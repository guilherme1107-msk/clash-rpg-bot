"""Persistência SQLite do bot."""

from __future__ import annotations

import json
import sqlite3
import threading

from src.domain.combat import Skill, SkillEffect, clamp_sp
from src.domain.status import CombatStatus, STATUS_TYPES, TREMOR_TYPES, on_round_end

# Uso por rodada dos efeitos com limite (SkillEffect.max_per_round).
# Vive só em memória — zera junto com a rodada em process_round_end_statuses.
_ROUND_USAGE: dict[tuple, int] = {}

# Flag de Amplitude Conversion (EGO_GIFTS 1.5). Enquanto ligado, TODO Tremor
# nasce como Tremor-Scorch — inclusive o aplicado por outras fontes. Desliga
# quando o Count do Tremor chega a 0 (aí a linha é apagada e o próximo Tremor
# volta a nascer "normal"). Vive em memória: um reinício do bot no meio da
# luta perde o flag até o próximo Clash Win converter de novo.
_AMPLITUDE_FLAGS: set[tuple] = set()


def _effects_json(skill: Skill) -> str:
    return json.dumps([
        {"trigger": effect.trigger, "effect_type": effect.effect_type, "value": effect.value,
         "coin": effect.coin, "count": effect.count, "charge_cost": effect.charge_cost,
         "condition_status": effect.condition_status, "condition_min": effect.condition_min,
         "condition_owner": effect.condition_owner, "condition_value": effect.condition_value,
         "condition_per": effect.condition_per,
         "condition_max_stacks": effect.condition_max_stacks,
         "consume_condition": effect.consume_condition,
         "effect_owner": effect.effect_owner,
         "condition_operator": effect.condition_operator}
        for effect in skill.effects
    ], ensure_ascii=False)


# §7.5 do desenho — a keyword é **rótulo de sistema**; a tela continua com o
# nome próprio. Hoje há 1 caso: a Falsa Fome da Rosemary vale como
# `unique_bloodfeast` para os gifts, mas continua aparecendo "Falsa Fome".
# Se aparecer mais, vira dado em tabela (não código).
KEYWORD_ALIASES = {"false_hunger": "unique_bloodfeast"}

# §7.7 — teto de gifts por Uptie (decisão 9 do autor). VAZIO de propósito: ele
# lembra que Uptie 5 dá "10–12", mas não os dos níveis 1 a 4. Enquanto estiver
# vazio, **nada muda** — a lista livre de hoje continua valendo.
EGO_GIFT_MAX_BY_UPTIE: dict[int, int] = {}   # ex.: {1: 2, 2: 4, 3: 6, 4: 8, 5: 12}


def normalize_keywords(raw) -> frozenset[str]:
    """Keywords da ficha em forma canônica: minúsculas, sem vazios, alias aplicado.

    Aceita a lista pronta ou o JSON gravado na coluna. Uma string simples (o
    caso ``"false_hunger"``) vira uma keyword só; lixo vira conjunto vazio —
    nunca exceção, senão uma ficha mal gravada derrubaria o meio do combate.
    """
    if isinstance(raw, (list, tuple, set)):
        items = list(raw)
    elif isinstance(raw, str):
        try:
            items = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            items = []
        if isinstance(items, str):
            items = [items]
    else:
        items = []
    if not isinstance(items, list):
        items = []
    out = set()
    for item in items:
        kw = str(item).strip().casefold()
        if kw:
            out.add(KEYWORD_ALIASES.get(kw, kw))
    return frozenset(out)


def _gift_gate_ok(row, owner_keywords: frozenset[str], count_allies) -> bool:
    """Bloco 7 — *"o gift só vale quando…"*. Vazio = sempre vale.

    - ``active_status``: keyword que a **própria ficha** precisa declarar;
    - ``active_tag`` + ``active_scope='allies'``: quantos **sinners do
      encontro** precisam declarar essa keyword — é o *"3 ou mais aliados da
      Middle/Poise"*. **O próprio conta**, como o Limbus escreve. ``active_min``
      é esse total (0 → 1);
    - ``active_scope='self'`` (padrão) não olha aliados nenhum.
    """
    if "active_status" not in row.keys():
        return True   # linha gravada antes da migração
    status = str(row["active_status"] or "").strip().casefold()
    if status and status not in owner_keywords:
        return False
    tag = str(row["active_tag"] or "").strip().casefold()
    if tag and str(row["active_scope"] or "self") != "self":
        need = max(1, int(row["active_min"] or 0))
        if count_allies(tag) < need:
            return False
    return True


def _effects_from_row(row) -> tuple[SkillEffect, ...]:
    """``effects_json`` -> efeitos. Cláusula ruim é descartada **uma a uma**.

    Antes o ``try`` embrulhava a lista inteira: uma única cláusula inválida
    devolvia ``()`` e apagava as outras em silêncio — o gift ficava invisível
    sem nenhum aviso. Aqui só a cláusula ruim some, e o resto continua
    valendo; assim nenhuma entrada mal escrita derruba o meio do combate.
    """
    if "effects_json" not in row.keys():
        return ()
    try:
        items = json.loads(row["effects_json"] or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    if not isinstance(items, list):
        return ()
    effects: list[SkillEffect] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            if item.get("effect_type") == "false_hunger":
                # A Falsa Fome É um Unique Bloodfeast (decisão do autor): as
                # skills da Rosemary speak `bloodfeast` direto, senão o E.G.O
                # Gift não enxerga o recurso que elas consomem.
                item["effect_type"] = "bloodfeast"
            if item.get("condition_status") == "false_hunger":
                item["condition_status"] = "bloodfeast"
            effects.append(SkillEffect(**item))
        except (TypeError, ValueError):
            continue  # cláusula inválida cai sozinha, sem levar as outras junto
    return tuple(effects)


def _coin_layout_json(skill: Skill) -> str:
    return json.dumps(list(skill.coin_layout))


def _coin_layout_from_row(row) -> tuple[str, ...]:
    if "coin_layout_json" not in row.keys():
        return ()
    try:
        layout = tuple(json.loads(row["coin_layout_json"] or "[]"))
        return layout if len(layout) == row["coins"] else ()
    except (TypeError, json.JSONDecodeError):
        return ()


class Database:
    def __init__(self, path: str) -> None:
        self.connection = sqlite3.connect(path, timeout=15, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        # Bot, Activity e Central podem tocar o mesmo banco. WAL permite
        # leituras durante uma gravação e busy_timeout evita falhas transitórias
        # quando duas ações chegam quase ao mesmo tempo.
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")
        self.connection.execute("PRAGMA busy_timeout = 15000")
        self.lock = threading.Lock()
        self.last_round_status_events = []
        # Gancho dos gatilhos `session_*` dos E.G.O Gifts (Etapa 4). O banco é
        # puro e não importa o bot, então quem liga o callback é o bot
        # (`bot.py`); enquanto ninguém ligar, nada acontece e o fluxo antigo
        # continua igual. A assinatura é
        # ``(guild_id, channel_id, trigger, turn)``.
        self.session_hook = None

    def setup(self) -> None:
        with self.lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS characters (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    sp INTEGER NOT NULL DEFAULT 0 CHECK(sp BETWEEN -45 AND 45),
                    offense_level INTEGER NOT NULL DEFAULT 0,
                    defense_level INTEGER NOT NULL DEFAULT 0,
                    paralysis INTEGER NOT NULL DEFAULT 0,
                    base_power_mod INTEGER NOT NULL DEFAULT 0,
                    coin_power_mod INTEGER NOT NULL DEFAULT 0,
                    clash_power_mod INTEGER NOT NULL DEFAULT 0,
                    offense_level_mod INTEGER NOT NULL DEFAULT 0,
                    defense_level_mod INTEGER NOT NULL DEFAULT 0,
                    charge_potency_enabled INTEGER NOT NULL DEFAULT 0,
                    charge_spent INTEGER NOT NULL DEFAULT 0,
                    special_condition_consumed INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL COLLATE NOCASE,
                    base_power INTEGER NOT NULL,
                    coin_power INTEGER NOT NULL,
                    coins INTEGER NOT NULL CHECK(coins BETWEEN 1 AND 10),
                    unbreakable_coins INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    effects_json TEXT NOT NULL DEFAULT '[]',
                    coin_layout_json TEXT NOT NULL DEFAULT '[]',
                    level_type TEXT NOT NULL DEFAULT 'offense',
                    skill_slot TEXT NOT NULL DEFAULT '',
                    UNIQUE (guild_id, owner_id, name)
                );
                CREATE TABLE IF NOT EXISTS enemies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL COLLATE NOCASE,
                    sp INTEGER NOT NULL DEFAULT 0 CHECK(sp BETWEEN -45 AND 45),
                    offense_level INTEGER NOT NULL DEFAULT 0,
                    defense_level INTEGER NOT NULL DEFAULT 0,
                    uses_sanity INTEGER NOT NULL DEFAULT 1,
                    paralysis INTEGER NOT NULL DEFAULT 0,
                    base_power_mod INTEGER NOT NULL DEFAULT 0,
                    coin_power_mod INTEGER NOT NULL DEFAULT 0,
                    clash_power_mod INTEGER NOT NULL DEFAULT 0,
                    offense_level_mod INTEGER NOT NULL DEFAULT 0,
                    defense_level_mod INTEGER NOT NULL DEFAULT 0,
                    charge_potency_enabled INTEGER NOT NULL DEFAULT 0,
                    charge_spent INTEGER NOT NULL DEFAULT 0,
                    special_condition_consumed INTEGER NOT NULL DEFAULT 0,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    created_by INTEGER NOT NULL,
                    UNIQUE (guild_id, name)
                );
                CREATE TABLE IF NOT EXISTS enemy_skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    enemy_id INTEGER NOT NULL REFERENCES enemies(id) ON DELETE CASCADE,
                    name TEXT NOT NULL COLLATE NOCASE,
                    base_power INTEGER NOT NULL,
                    coin_power INTEGER NOT NULL,
                    coins INTEGER NOT NULL CHECK(coins BETWEEN 1 AND 10),
                    unbreakable_coins INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    effects_json TEXT NOT NULL DEFAULT '[]',
                    coin_layout_json TEXT NOT NULL DEFAULT '[]',
                    skill_type TEXT NOT NULL DEFAULT 'attack',
                    skill_slot TEXT NOT NULL DEFAULT '',
                    UNIQUE (enemy_id, name)
                );
                CREATE TABLE IF NOT EXISTS battle_sessions (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    turn INTEGER NOT NULL DEFAULT 1,
                    created_by INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    panel_message_id INTEGER,
                    phase TEXT NOT NULL DEFAULT 'preparation',
                    PRIMARY KEY (guild_id, channel_id)
                );
                CREATE TABLE IF NOT EXISTS battle_field_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    enemy_name TEXT NOT NULL,
                    enemy_group_member_id INTEGER,
                    enemy_skill TEXT NOT NULL,
                    target_user_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'open',
                    claimed_by INTEGER,
                    player_skill TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (guild_id, channel_id)
                        REFERENCES battle_sessions(guild_id, channel_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS battle_participants (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    character_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'waiting',
                    ready INTEGER NOT NULL DEFAULT 0,
                    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, channel_id, user_id),
                    FOREIGN KEY (guild_id, channel_id)
                        REFERENCES battle_sessions(guild_id, channel_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS battle_player_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    character_name TEXT NOT NULL,
                    target_enemy TEXT NOT NULL,
                    player_skill TEXT NOT NULL,
                    action_type TEXT NOT NULL DEFAULT 'unopposed',
                    final_damage INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (guild_id, channel_id)
                        REFERENCES battle_sessions(guild_id, channel_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS battle_enemy_free_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    enemy_id INTEGER NOT NULL,
                    enemy_group_member_id INTEGER,
                    enemy_skill TEXT NOT NULL,
                    target_user_id INTEGER NOT NULL,
                    variant TEXT NOT NULL DEFAULT 'unopposed',
                    status TEXT NOT NULL DEFAULT 'pending',
                    final_damage INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (guild_id, channel_id) REFERENCES battle_sessions(guild_id, channel_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS enemy_group_member_statuses (
                    member_id INTEGER NOT NULL REFERENCES enemy_group_members(id) ON DELETE CASCADE,
                    status_type TEXT NOT NULL,
                    potency INTEGER NOT NULL DEFAULT 0 CHECK(potency >= 0),
                    count INTEGER NOT NULL DEFAULT 0 CHECK(count >= 0),
                    tremor_type TEXT NOT NULL DEFAULT 'normal',
                    PRIMARY KEY(member_id,status_type)
                );
                CREATE TABLE IF NOT EXISTS enemy_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL COLLATE NOCASE,
                    template_enemy_id INTEGER NOT NULL REFERENCES enemies(id) ON DELETE RESTRICT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(guild_id, name)
                );
                CREATE TABLE IF NOT EXISTS enemy_group_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL REFERENCES enemy_groups(id) ON DELETE CASCADE,
                    member_name TEXT NOT NULL,
                    hp INTEGER NOT NULL DEFAULT 100 CHECK(hp >= 0),
                    hp_max INTEGER NOT NULL DEFAULT 100 CHECK(hp_max > 0),
                    sp INTEGER NOT NULL DEFAULT 0 CHECK(sp BETWEEN -45 AND 45),
                    paralysis INTEGER NOT NULL DEFAULT 0,
                    base_power_mod INTEGER NOT NULL DEFAULT 0,
                    coin_power_mod INTEGER NOT NULL DEFAULT 0,
                    clash_power_mod INTEGER NOT NULL DEFAULT 0,
                    offense_level_mod INTEGER NOT NULL DEFAULT 0,
                    defense_level_mod INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(group_id, member_name)
                );
                CREATE TABLE IF NOT EXISTS discord_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    sent_at TEXT
                );
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    audit_channel_id INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS clash_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL DEFAULT 0,
                    requester_id INTEGER NOT NULL,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result_json TEXT,
                    error TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS passives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    owner_kind TEXT NOT NULL DEFAULT 'player',
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    effects_json TEXT NOT NULL DEFAULT '[]',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS ego_gifts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    owner_kind TEXT NOT NULL DEFAULT 'player',
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    tier INTEGER NOT NULL DEFAULT 1,
                    description TEXT NOT NULL DEFAULT '',
                    effects_json TEXT NOT NULL DEFAULT '[]',
                    base_power_mod INTEGER NOT NULL DEFAULT 0,
                    coin_power_mod INTEGER NOT NULL DEFAULT 0,
                    clash_power_mod INTEGER NOT NULL DEFAULT 0,
                    offense_level_mod INTEGER NOT NULL DEFAULT 0,
                    defense_level_mod INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                -- Etapa 5 — duração e limite dos E.G.O Gifts (§9.3 do desenho).
                -- Uma linha = um efeito que o gift deixou PENDENTE para os
                -- inícios de rodada seguintes. Serve para as duas coisas:
                -- "por 2 Rodadas" (expires_turn) e "1x por rodada"
                -- (window_key + activations_left).
                CREATE TABLE IF NOT EXISTS ego_gift_state (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id          INTEGER NOT NULL,
                    owner_kind        TEXT NOT NULL,
                    owner_id          INTEGER NOT NULL,
                    gift_name         TEXT NOT NULL DEFAULT '',
                    effect_type       TEXT NOT NULL,
                    value             REAL NOT NULL DEFAULT 0,
                    effect_owner      TEXT NOT NULL DEFAULT 'user',
                    gift_tag          TEXT NOT NULL DEFAULT '',
                    starts_turn       INTEGER NOT NULL DEFAULT 0,
                    expires_turn      INTEGER NOT NULL DEFAULT 0,  -- 0 = não expira
                    window_key        TEXT NOT NULL DEFAULT '',     -- 'round:7' | 'combat'
                    activations_left  INTEGER,                      -- NULL = sem limite
                    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (guild_id, owner_kind, owner_id, gift_name, effect_type,
                            window_key, expires_turn)
                );
                CREATE INDEX IF NOT EXISTS ego_gift_state_owner_idx
                    ON ego_gift_state(guild_id, owner_kind, owner_id);
                CREATE TABLE IF NOT EXISTS core_entity_versions (
                    guild_id INTEGER NOT NULL,
                    entity_kind TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, entity_kind, entity_id)
                );
                CREATE TABLE IF NOT EXISTS core_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL UNIQUE,
                    guild_id INTEGER NOT NULL,
                    command TEXT NOT NULL,
                    source TEXT NOT NULL,
                    entity_kind TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'committed',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS core_events_entity_idx
                    ON core_events(guild_id, entity_kind, entity_id, id DESC);
                CREATE TABLE IF NOT EXISTS composer_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    channel_name TEXT NOT NULL DEFAULT '',
                    message_id INTEGER NOT NULL UNIQUE,
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'sent',
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT,
                    deleted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS composer_messages_guild_idx
                    ON composer_messages(guild_id, status, id DESC);
                CREATE TABLE IF NOT EXISTS combat_statuses (
                    guild_id INTEGER NOT NULL,
                    owner_kind TEXT NOT NULL CHECK(owner_kind IN ('player','enemy')),
                    owner_id INTEGER NOT NULL,
                    status_type TEXT NOT NULL,
                    potency INTEGER NOT NULL DEFAULT 0 CHECK(potency >= 0),
                    count INTEGER NOT NULL DEFAULT 0 CHECK(count >= 0),
                    tremor_type TEXT NOT NULL DEFAULT 'normal',
                    PRIMARY KEY (guild_id, owner_kind, owner_id, status_type)
                );
                CREATE TABLE IF NOT EXISTS rosemary_states (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    seals INTEGER NOT NULL DEFAULT 3 CHECK(seals BETWEEN 0 AND 3),
                    unpacked INTEGER NOT NULL DEFAULT 0,
                    false_hunger_max INTEGER NOT NULL DEFAULT 100,
                    false_hunger_consumed_total INTEGER NOT NULL DEFAULT 0,
                    devotion_max INTEGER NOT NULL DEFAULT 1,
                    haste_pending INTEGER NOT NULL DEFAULT 0,
                    haste_active INTEGER NOT NULL DEFAULT 0,
                    hp_trigger_used INTEGER NOT NULL DEFAULT 0,
                    hunger_coin_active INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS rosemary_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL,
                    amount INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS guild_registry (
                    guild_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profile_appearance (
                    guild_id INTEGER NOT NULL,
                    owner_kind TEXT NOT NULL CHECK(owner_kind IN ('player','enemy')),
                    owner_id INTEGER NOT NULL,
                    image_url TEXT NOT NULL DEFAULT '',
                    accent_color TEXT NOT NULL DEFAULT '#b31824',
                    subtitle TEXT NOT NULL DEFAULT '',
                    secondary_color TEXT NOT NULL DEFAULT '#17181a',
                    image_mode TEXT NOT NULL DEFAULT 'banner',
                    image_position TEXT NOT NULL DEFAULT 'center',
                    footer_text TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (guild_id, owner_kind, owner_id)
                );
                CREATE TABLE IF NOT EXISTS character_profiles (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    profile_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id),
                    FOREIGN KEY (guild_id, user_id) REFERENCES characters(guild_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS media_upload_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    owner_kind TEXT NOT NULL CHECK(owner_kind IN ('player','enemy')),
                    owner_id INTEGER NOT NULL,
                    source_url TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result_url TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            # Migração de bancos criados pela primeira versão.
            character_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(characters)")}
            for name, definition in {
                "offense_level": "INTEGER NOT NULL DEFAULT 0",
                "defense_level": "INTEGER NOT NULL DEFAULT 0",
                "paralysis": "INTEGER NOT NULL DEFAULT 0",
                "base_power_mod": "INTEGER NOT NULL DEFAULT 0",
                "coin_power_mod": "INTEGER NOT NULL DEFAULT 0",
                "clash_power_mod": "INTEGER NOT NULL DEFAULT 0",
                "offense_level_mod": "INTEGER NOT NULL DEFAULT 0",
                "defense_level_mod": "INTEGER NOT NULL DEFAULT 0",
                "charge_potency_enabled": "INTEGER NOT NULL DEFAULT 0",
                "charge_spent": "INTEGER NOT NULL DEFAULT 0",
                "special_condition_consumed": "INTEGER NOT NULL DEFAULT 0",
                # Espelho do de cima para o Bloodfeast: a Rosemary consumia a
                # Falsa Fome pelas skills e as condições olhavam o "já
                # consumido". Passou a speak `bloodfeast`.
                "bloodfeast_consumed": "INTEGER NOT NULL DEFAULT 0",
                "tags_json": "TEXT NOT NULL DEFAULT '[]'",
                "keywords": "TEXT NOT NULL DEFAULT '[]'",
            }.items():
                if name not in character_columns:
                    self.connection.execute(f"ALTER TABLE characters ADD COLUMN {name} {definition}")
            rosemary_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(rosemary_states)")}
            for name, definition in {
                "devotion_max": "INTEGER NOT NULL DEFAULT 1",
                "haste_pending": "INTEGER NOT NULL DEFAULT 0",
                "haste_active": "INTEGER NOT NULL DEFAULT 0",
                "hp_trigger_used": "INTEGER NOT NULL DEFAULT 0",
                "hunger_coin_active": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in rosemary_columns:
                    self.connection.execute(f"ALTER TABLE rosemary_states ADD COLUMN {name} {definition}")
            skill_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(skills)")}
            if "level_type" not in skill_columns:
                self.connection.execute("ALTER TABLE skills ADD COLUMN level_type TEXT NOT NULL DEFAULT 'offense'")
            if "unbreakable_coins" not in skill_columns:
                self.connection.execute("ALTER TABLE skills ADD COLUMN unbreakable_coins INTEGER NOT NULL DEFAULT 0")
            if "effects_json" not in skill_columns:
                self.connection.execute("ALTER TABLE skills ADD COLUMN effects_json TEXT NOT NULL DEFAULT '[]'")
            if "coin_layout_json" not in skill_columns:
                self.connection.execute("ALTER TABLE skills ADD COLUMN coin_layout_json TEXT NOT NULL DEFAULT '[]'")
            if "skill_slot" not in skill_columns:
                self.connection.execute("ALTER TABLE skills ADD COLUMN skill_slot TEXT NOT NULL DEFAULT ''")
            # Amplitude Conversion: a variante do Tremor mora na própria linha
            # para preservar Potência/Count ao converter.
            for status_table in ("combat_statuses", "enemy_group_member_statuses"):
                status_columns = {r[1] for r in self.connection.execute(f"PRAGMA table_info({status_table})")}
                if "tremor_type" not in status_columns:
                    self.connection.execute(
                        f"ALTER TABLE {status_table} ADD COLUMN tremor_type TEXT NOT NULL DEFAULT 'normal'"
                    )
            enemy_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(enemies)")}
            if "uses_sanity" not in enemy_columns:
                self.connection.execute("ALTER TABLE enemies ADD COLUMN uses_sanity INTEGER NOT NULL DEFAULT 1")
            if "defense_level" not in enemy_columns:
                self.connection.execute("ALTER TABLE enemies ADD COLUMN defense_level INTEGER NOT NULL DEFAULT 0")
            for name in (
                "paralysis", "base_power_mod", "coin_power_mod", "clash_power_mod",
                "offense_level_mod", "defense_level_mod",
            ):
                if name not in enemy_columns:
                    self.connection.execute(f"ALTER TABLE enemies ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
            for name, definition in {
                "charge_potency_enabled": "INTEGER NOT NULL DEFAULT 0",
                "charge_spent": "INTEGER NOT NULL DEFAULT 0",
                "special_condition_consumed": "INTEGER NOT NULL DEFAULT 0",
                "bloodfeast_consumed": "INTEGER NOT NULL DEFAULT 0",
                "tags_json": "TEXT NOT NULL DEFAULT '[]'",
                "keywords": "TEXT NOT NULL DEFAULT '[]'",
            }.items():
                if name not in enemy_columns:
                    self.connection.execute(f"ALTER TABLE enemies ADD COLUMN {name} {definition}")
            # Bloco 7 — "o gift só vale quando…". Vazio = sempre vale, que é
            # exatamente o comportamento de antes; a migração só abre o espaço.
            gift_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(ego_gifts)")}
            for name, definition in {
                "active_status": "TEXT NOT NULL DEFAULT ''",
                "active_tag": "TEXT NOT NULL DEFAULT ''",
                "active_scope": "TEXT NOT NULL DEFAULT 'self'",
                "active_min": "INTEGER NOT NULL DEFAULT 0",
                # Classe do gift (HE, WAW, …). Vazio = a ficha não diz: é
                # metadado, não regra, e nada no motor le isso.
                "gift_class": "TEXT NOT NULL DEFAULT ''",
                # Clear Mirror, Calm Water: "Aumenta o Dano Crítico de todos os
                # aliados em +70%". Não é cláusula com gatilho: é um
                # modificador permanente, como os outros 5 — o §9.3 do desenho
                # previa exatamente somar "colunas fixas + linhas ativas".
                "crit_damage_mod": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in gift_columns:
                    self.connection.execute(f"ALTER TABLE ego_gifts ADD COLUMN {name} {definition}")
            # Bloodfiend/Bloodbag nasceram como status nas primeiras versões. Agora
            # são tags permanentes do hostil; a migração preserva as fichas antigas.
            legacy_markers = self.connection.execute(
                """SELECT owner_id,status_type FROM combat_statuses
                   WHERE owner_kind='enemy' AND status_type IN ('bloodfiend','bloodbag')
                   AND count>0"""
            ).fetchall()
            for marker in legacy_markers:
                enemy = self.connection.execute(
                    "SELECT tags_json FROM enemies WHERE id=?", (marker["owner_id"],)
                ).fetchone()
                if enemy is None:
                    continue
                try:
                    tags = list(json.loads(enemy["tags_json"] or "[]"))
                except (TypeError, json.JSONDecodeError):
                    tags = []
                if marker["status_type"] not in {tag.casefold() for tag in tags}:
                    tags.append(marker["status_type"])
                self.connection.execute(
                    "UPDATE enemies SET tags_json=? WHERE id=?",
                    (json.dumps(tags, ensure_ascii=False), marker["owner_id"]),
                )
            self.connection.execute(
                """DELETE FROM combat_statuses WHERE owner_kind='enemy'
                   AND status_type IN ('bloodfiend','bloodbag')"""
            )
            enemy_skill_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(enemy_skills)")}
            if "skill_type" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN skill_type TEXT NOT NULL DEFAULT 'attack'")
            if "unbreakable_coins" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN unbreakable_coins INTEGER NOT NULL DEFAULT 0")
            if "effects_json" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN effects_json TEXT NOT NULL DEFAULT '[]'")
            if "coin_layout_json" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN coin_layout_json TEXT NOT NULL DEFAULT '[]'")
            if "skill_slot" not in enemy_skill_columns:
                self.connection.execute("ALTER TABLE enemy_skills ADD COLUMN skill_slot TEXT NOT NULL DEFAULT ''")
            defense_types = {"guard", "evade", "counter", "clashable_guard", "clashable_counter", "assist_defense", "defense"}
            for table, owner_column, type_column in (("skills", "owner_id", "level_type"), ("enemy_skills", "enemy_id", "skill_type")):
                rows = self.connection.execute(f"SELECT id,{owner_column},{type_column},skill_slot FROM {table} ORDER BY {owner_column},id").fetchall()
                counters = {}
                for row in rows:
                    if row["skill_slot"]:
                        continue
                    owner = row[owner_column]; defensive = row[type_column] in defense_types
                    key = (owner, defensive); counters[key] = counters.get(key, 0) + 1; position = counters[key]
                    slot = f"d{position}" if defensive else (f"s{position}" if position <= 3 else f"s3-{position - 3}")
                    self.connection.execute(f"UPDATE {table} SET skill_slot=? WHERE id=?", (slot, row["id"]))
            battle_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(battle_sessions)")}
            if "phase" not in battle_columns:
                self.connection.execute(
                    "ALTER TABLE battle_sessions ADD COLUMN phase TEXT NOT NULL DEFAULT 'preparation'"
                )
            participant_columns = {
                r[1] for r in self.connection.execute("PRAGMA table_info(battle_participants)")
            }
            if "ready" not in participant_columns:
                self.connection.execute(
                    "ALTER TABLE battle_participants ADD COLUMN ready INTEGER NOT NULL DEFAULT 0"
                )
            battle_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(battle_sessions)")}
            if "panel_message_id" not in battle_columns:
                self.connection.execute("ALTER TABLE battle_sessions ADD COLUMN panel_message_id INTEGER")
            field_action_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(battle_field_actions)")}
            if "target_user_id" not in field_action_columns:
                self.connection.execute("ALTER TABLE battle_field_actions ADD COLUMN target_user_id INTEGER")
            if "enemy_group_member_id" not in field_action_columns:
                self.connection.execute("ALTER TABLE battle_field_actions ADD COLUMN enemy_group_member_id INTEGER")
            free_action_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(battle_enemy_free_actions)")}
            if "enemy_group_member_id" not in free_action_columns:
                self.connection.execute("ALTER TABLE battle_enemy_free_actions ADD COLUMN enemy_group_member_id INTEGER")
            settings_columns = {r[1] for r in self.connection.execute("PRAGMA table_info(guild_settings)")}
            if "clash_channel_id" not in settings_columns:
                self.connection.execute("ALTER TABLE guild_settings ADD COLUMN clash_channel_id INTEGER NOT NULL DEFAULT 0")
            appearance_columns = {
                row[1] for row in self.connection.execute("PRAGMA table_info(profile_appearance)")
            }
            for name, definition in {
                "secondary_color": "TEXT NOT NULL DEFAULT '#17181a'",
                "image_mode": "TEXT NOT NULL DEFAULT 'banner'",
                "image_position": "TEXT NOT NULL DEFAULT 'center'",
                "footer_text": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if name not in appearance_columns:
                    self.connection.execute(f"ALTER TABLE profile_appearance ADD COLUMN {name} {definition}")
            # Status sem Count não permanece guardado: isso impede que uma
            # aplicação futura apenas de Count recupere Potência antiga.
            self.connection.execute(
                """UPDATE combat_statuses SET status_type='special_condition'
                   WHERE status_type='false_hunger' AND NOT EXISTS (
                       SELECT 1 FROM combat_statuses AS current
                       WHERE current.guild_id=combat_statuses.guild_id
                         AND current.owner_kind=combat_statuses.owner_kind
                         AND current.owner_id=combat_statuses.owner_id
                         AND current.status_type='special_condition'
                   )"""
            )
            self.connection.execute("DELETE FROM combat_statuses WHERE status_type='false_hunger'")
            self.connection.execute("DELETE FROM combat_statuses WHERE count<=0")
            # Versões antigas podiam gravar modificadores temporários (como
            # coin_power) na tabela de Status. Eles não são condições de
            # combate e não podem impedir a passagem da rodada.
            valid_statuses = tuple(sorted(STATUS_TYPES))
            placeholders = ",".join("?" for _ in valid_statuses)
            self.connection.execute(
                f"DELETE FROM combat_statuses WHERE status_type NOT IN ({placeholders})",
                valid_statuses,
            )
            self.connection.execute("UPDATE discord_outbox SET status='pending' WHERE status='processing' AND attempts<5")
            self.connection.execute("UPDATE clash_jobs SET status='pending',updated_at=CURRENT_TIMESTAMP WHERE status='processing' AND attempts<3")

    def __enter__(self) -> Database:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        with self.lock:
            try:
                self.connection.close()
            except Exception:
                pass


    def enqueue_discord_event(self, guild_id: int, channel_id: int, event_type: str, payload: dict) -> int:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "INSERT INTO discord_outbox(guild_id,channel_id,event_type,payload_json) VALUES(?,?,?,?)",
                (guild_id, channel_id, event_type, json.dumps(payload, ensure_ascii=False)),
            )
            return int(cursor.lastrowid)

    def claim_discord_events(self, limit: int = 10):
        with self.lock, self.connection:
            rows = self.connection.execute(
                "SELECT * FROM discord_outbox WHERE status='pending' AND attempts<5 ORDER BY id LIMIT ?", (limit,),
            ).fetchall()
            self.connection.executemany(
                "UPDATE discord_outbox SET status='processing',attempts=attempts+1 WHERE id=?",
                [(row["id"],) for row in rows],
            )
            return rows

    def finish_discord_event(self, event_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute("UPDATE discord_outbox SET status='sent',sent_at=CURRENT_TIMESTAMP,error='' WHERE id=?", (event_id,))

    def fail_discord_event(self, event_id: int, error: str) -> None:
        with self.lock, self.connection:
            self.connection.execute("UPDATE discord_outbox SET status='pending',error=? WHERE id=?", (error[:500], event_id))

    def enqueue_clash_job(self, guild_id: int, channel_id: int, requester_id: int, request: dict) -> int:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "INSERT INTO clash_jobs(guild_id,channel_id,requester_id,request_json) VALUES(?,?,?,?)",
                (guild_id, channel_id, requester_id, json.dumps(request, ensure_ascii=False)),
            )
            return int(cursor.lastrowid)

    def claim_clash_jobs(self, limit: int = 5):
        with self.lock, self.connection:
            rows = self.connection.execute(
                "SELECT * FROM clash_jobs WHERE status='pending' AND attempts<3 ORDER BY id LIMIT ?", (limit,),
            ).fetchall()
            self.connection.executemany(
                "UPDATE clash_jobs SET status='processing',attempts=attempts+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
                [(row["id"],) for row in rows],
            )
            return rows

    def get_clash_job(self, job_id: int):
        with self.lock:
            return self.connection.execute("SELECT * FROM clash_jobs WHERE id=?", (job_id,)).fetchone()

    def finish_clash_job(self, job_id: int, result: dict) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE clash_jobs SET status='completed',result_json=?,error='',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(result, ensure_ascii=False), job_id),
            )

    def fail_clash_job(self, job_id: int, error: str) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE clash_jobs SET status='failed',error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (error[:500], job_id),
            )

    def cancel_clash_job(self, job_id: int) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "UPDATE clash_jobs SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'", (job_id,),
            )
            return cursor.rowcount > 0

    def save_guild(self, guild_id: int, name: str) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO guild_registry(guild_id,name) VALUES(?,?)
                   ON CONFLICT(guild_id) DO UPDATE SET name=excluded.name""",
                (guild_id, name[:100]),
            )

    def get_appearance(self, guild_id: int, owner_kind: str, owner_id: int):
        # A Central guarda uploads locais em profile_appearance para que a arte
        # nunca dependa de uma URL assinada do CDN do Discord. Para embeds do
        # bot, trocamos essa origem local pela cópia mais recente publicada no
        # canal-cofre.
        with self.lock:
            return self.connection.execute(
                """SELECT CASE
                             WHEN image_url LIKE '/uploads/%' THEN COALESCE(
                               (SELECT NULLIF(result_url,'') FROM media_upload_jobs
                                WHERE guild_id=profile_appearance.guild_id
                                  AND owner_kind=profile_appearance.owner_kind
                                  AND owner_id=profile_appearance.owner_id
                                  AND status='complete'
                                ORDER BY id DESC LIMIT 1),
                               image_url
                             ) ELSE image_url END AS image_url,
                          accent_color,subtitle,secondary_color,image_mode,
                          image_position,footer_text FROM profile_appearance
                   WHERE guild_id=? AND owner_kind=? AND owner_id=?""",
                (guild_id, owner_kind, owner_id),
            ).fetchone()

    def save_appearance(
        self, guild_id: int, owner_kind: str, owner_id: int,
        image_url: str, accent_color: str, subtitle: str,
        secondary_color: str | None = None, image_mode: str | None = None,
        image_position: str | None = None, footer_text: str | None = None,
    ) -> None:
        if owner_kind not in {"player", "enemy", "enemy_group"}:
            raise ValueError("Tipo de ficha inválido.")
        current = self.get_appearance(guild_id, owner_kind, owner_id)
        secondary_color = secondary_color or (current["secondary_color"] if current else "#17181a")
        image_mode = image_mode or (current["image_mode"] if current else "banner")
        image_position = image_position or (current["image_position"] if current else "center")
        footer_text = footer_text if footer_text is not None else (current["footer_text"] if current else "")
        if image_mode not in {"banner", "thumbnail", "none"}:
            raise ValueError("Modo de imagem inválido.")
        if image_position not in {"center", "top", "bottom", "left", "right"}:
            raise ValueError("Posição da imagem inválida.")
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO profile_appearance
                   (guild_id,owner_kind,owner_id,image_url,accent_color,subtitle,
                    secondary_color,image_mode,image_position,footer_text)
                   VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(guild_id,owner_kind,owner_id)
                   DO UPDATE SET image_url=excluded.image_url,
                                 accent_color=excluded.accent_color,
                                 subtitle=excluded.subtitle,
                                 secondary_color=excluded.secondary_color,
                                 image_mode=excluded.image_mode,
                                 image_position=excluded.image_position,
                                 footer_text=excluded.footer_text""",
                (guild_id, owner_kind, owner_id, image_url[:1000], accent_color[:7], subtitle[:120],
                 secondary_color[:7], image_mode, image_position, footer_text[:160]),
            )

    def queue_media_upload(
        self, guild_id: int, owner_kind: str, owner_id: int, source_url: str,
    ) -> int:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE media_upload_jobs SET status='superseded',updated_at=CURRENT_TIMESTAMP
                   WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status='pending'""",
                (guild_id, owner_kind, owner_id),
            )
            cursor = self.connection.execute(
                """INSERT INTO media_upload_jobs(guild_id,owner_kind,owner_id,source_url)
                   VALUES(?,?,?,?)""",
                (guild_id, owner_kind, owner_id, source_url[:1000]),
            )
        return int(cursor.lastrowid)

    def pending_media_uploads(self, limit: int = 5):
        with self.lock:
            return self.connection.execute(
                """SELECT * FROM media_upload_jobs WHERE status='pending'
                   ORDER BY id LIMIT ?""", (limit,),
            ).fetchall()

    def finish_media_upload(self, job_id: int, result_url: str) -> None:
        with self.lock, self.connection:
            job = self.connection.execute(
                "SELECT * FROM media_upload_jobs WHERE id=?", (job_id,),
            ).fetchone()
            if job is None or job["status"] != "pending":
                return
            self.connection.execute(
                """UPDATE media_upload_jobs SET status='complete',result_url=?,error='',
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""", (result_url, job_id),
            )

    def fail_media_upload(self, job_id: int, error: str) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE media_upload_jobs SET status='failed',error=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""", (error[:500], job_id),
            )

    def set_status(
        self, guild_id: int, owner_kind: str, owner_id: int, status_type: str,
        potency: int, count: int,
    ) -> CombatStatus:
        if owner_kind not in {"player", "enemy", "enemy_group_member"}:
            raise ValueError("Dono de status inválido.")
        if status_type not in STATUS_TYPES:
            raise ValueError("Status inválido.")
        if count <= 0 and status_type == "tremor":
            # Count zerou -> a linha some e a Amplitude Conversion expira junto:
            # o próximo Tremor volta a nascer "normal" de novo.
            _AMPLITUDE_FLAGS.discard((guild_id, owner_kind, owner_id))
        if count <= 0:
            with self.lock, self.connection:
                if owner_kind == "enemy_group_member":
                    self.connection.execute(
                        "DELETE FROM enemy_group_member_statuses WHERE member_id=? AND status_type=?",
                        (owner_id, status_type),
                    )
                else:
                    self.connection.execute(
                        """DELETE FROM combat_statuses
                           WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status_type=?""",
                        (guild_id, owner_kind, owner_id, status_type),
                    )
            return CombatStatus(status_type, 0, 0)
        # Flag ligado -> TODO Tremor nasce como Tremor-Scorch, mesmo o que vem
        # de outra fonte. Uma linha já existente mantém o tipo que já tem; o
        # que muda aqui é a CRIAÇÃO da linha.
        tremor_type = (
            "scorch"
            if status_type == "tremor"
            and (guild_id, owner_kind, owner_id) in _AMPLITUDE_FLAGS
            else "normal"
        )
        status = CombatStatus(status_type, potency, count, tremor_type)
        with self.lock, self.connection:
            if owner_kind == "enemy_group_member":
                # tremor_type entra SÓ na criação; o ON CONFLICT continua
                # mexendo só em potency/count pra não apagar uma conversão
                # que a linha já tinha.
                self.connection.execute(
                    "INSERT INTO enemy_group_member_statuses(member_id,status_type,potency,count,tremor_type) VALUES(?,?,?,?,?) ON CONFLICT(member_id,status_type) DO UPDATE SET potency=excluded.potency,count=excluded.count",
                    (owner_id, status_type, potency, count, status.tremor_type),
                )
            else:
                self.connection.execute(
                    """INSERT INTO combat_statuses(guild_id,owner_kind,owner_id,status_type,potency,count,tremor_type)
                       VALUES(?,?,?,?,?,?,?) ON CONFLICT(guild_id,owner_kind,owner_id,status_type)
                       DO UPDATE SET potency=excluded.potency,count=excluded.count""",
                    (guild_id, owner_kind, owner_id, status.status_type,
                     status.potency, status.count, status.tremor_type),
                )
        return status

    def add_status(
        self, guild_id: int, owner_kind: str, owner_id: int, status_type: str,
        potency: int, count: int,
    ) -> CombatStatus:
        current = self.get_status(guild_id, owner_kind, owner_id, status_type)
        old_potency = current.potency if current else 0
        old_count = current.count if current else 0
        new_potency = old_potency + potency
        new_count = old_count + count
        # No Limbus, um status de dois valores precisa de ambos para formar sua
        # pilha inicial. Quando o Count acaba, set_status remove a linha inteira.
        already_exists = old_potency > 0 and old_count > 0
        if not already_exists:
            if new_potency > 0 and new_count == 0:
                new_count = 1
            elif new_count > 0 and new_potency == 0:
                new_potency = 1
        return self.set_status(
            guild_id, owner_kind, owner_id, status_type,
            new_potency, new_count,
        )

    def consume_charge(
        self, guild_id: int, owner_kind: str, owner_id: int, amount: int,
    ) -> tuple[CombatStatus, int, int]:
        """Consome Count e converte cada 10 gastos em Potência, quando habilitado.

        Retorna ``(charge_atual, potência_ganha, progresso_0_a_9)``.
        """
        if amount < 0:
            raise ValueError("O consumo de Charge não pode ser negativo.")
        charge = self.get_status(guild_id, owner_kind, owner_id, "charge")
        if charge is None or charge.count < amount:
            raise ValueError("Charge Count insuficiente.")
        if owner_kind == "enemy_group_member":
            new_count = charge.count - amount
            new_potency = charge.potency if new_count > 0 else 0
            saved = self.set_status(guild_id, owner_kind, owner_id, "charge", new_potency, new_count)
            return saved, 0, 0
        table, key = ("enemies", "id") if owner_kind == "enemy" else ("characters", "user_id")
        with self.lock:
            row = self.connection.execute(
                f"SELECT charge_potency_enabled,charge_spent FROM {table} WHERE guild_id=? AND {key}=?",
                (guild_id, owner_id),
            ).fetchone()
        if row is None:
            raise ValueError("Ficha não encontrada para consumir Charge.")
        enabled = bool(row["charge_potency_enabled"])
        accumulated = row["charge_spent"] + amount if enabled else 0
        potency_gain, progress = divmod(accumulated, 10) if enabled else (0, 0)
        new_count = charge.count - amount
        new_potency = charge.potency + potency_gain
        if new_count <= 0:
            new_potency = 0
        with self.lock, self.connection:
            self.connection.execute(
                f"UPDATE {table} SET charge_spent=? WHERE guild_id=? AND {key}=?",
                (progress, guild_id, owner_id),
            )
        saved = self.set_status(
            guild_id, owner_kind, owner_id, "charge", new_potency, new_count,
        )
        return saved, potency_gain, progress

    def get_resource_consumed(
        self, guild_id: int, owner_kind: str, owner_id: int, status_type: str,
    ) -> int:
        """Total consumido no Encounter atual de um recurso com contador.

        A coluna é ``<status>_consumed`` — `special_condition_consumed` e
        `bloodfeast_consumed` nasceram do mesmo molde.
        """
        if owner_kind not in {"player", "enemy"}:
            raise ValueError("Dono do recurso inválido.")
        column = f"{status_type}_consumed"
        table, key = ("enemies", "id") if owner_kind == "enemy" else ("characters", "user_id")
        with self.lock:
            row = self.connection.execute(
                f"SELECT {column} FROM {table} WHERE guild_id=? AND {key}=?",
                (guild_id, owner_id),
            ).fetchone()
        return 0 if row is None else int(row[column] or 0)

    def get_special_condition_consumed(
        self, guild_id: int, owner_kind: str, owner_id: int,
    ) -> int:
        """Total de Condição Especial consumido durante o Encounter atual."""
        return self.get_resource_consumed(guild_id, owner_kind, owner_id, "special_condition")

    def get_bloodfeast_consumed(
        self, guild_id: int, owner_kind: str, owner_id: int,
    ) -> int:
        """Total de Bloodfeast consumido no Encounter atual.

        A Rosemary consumia a Falsa Fome pelas skills; como ela é um Unique
        Bloodfeast, as skills dela speak `bloodfeast` e este é o "já consumido"
        que as condições consultam.
        """
        return self.get_resource_consumed(guild_id, owner_kind, owner_id, "bloodfeast")

    def consume_special_condition(
        self, guild_id: int, owner_kind: str, owner_id: int, maximum: int,
    ) -> tuple[CombatStatus, int, int]:
        """Consome até ``maximum`` de Count e registra o total do Encounter."""
        return self.consume_resource(guild_id, owner_kind, owner_id, "special_condition", maximum)

    def consume_bloodfeast(
        self, guild_id: int, owner_kind: str, owner_id: int, maximum: int,
    ) -> tuple[CombatStatus, int, int]:
        return self.consume_resource(guild_id, owner_kind, owner_id, "bloodfeast", maximum)

    def consume_resource(
        self, guild_id: int, owner_kind: str, owner_id: int,
        status_type: str, maximum: int,
    ) -> tuple[CombatStatus, int, int]:
        """Consome até ``maximum`` de Count e registra o total do Encounter."""
        if maximum < 0:
            raise ValueError("O consumo máximo não pode ser negativo.")
        current = self.get_status(guild_id, owner_kind, owner_id, status_type)
        amount = min(maximum, current.count if current else 0)
        if amount:
            saved = self.set_status(
                guild_id, owner_kind, owner_id, status_type,
                current.potency, current.count - amount,
            )
        else:
            saved = current or CombatStatus(status_type, 0, 0)
        table, key = ("enemies", "id") if owner_kind == "enemy" else ("characters", "user_id")
        column = f"{status_type}_consumed"
        with self.lock, self.connection:
            cursor = self.connection.execute(
                f"UPDATE {table} SET {column}={column}+? WHERE guild_id=? AND {key}=?",
                (amount, guild_id, owner_id),
            )
        if not cursor.rowcount:
            raise ValueError(f"Ficha não encontrada para consumir {status_type}.")
        return saved, amount, self.get_resource_consumed(guild_id, owner_kind, owner_id, status_type)

    def get_rosemary_state(self, guild_id: int, user_id: int):
        with self.lock, self.connection:
            existing = self.connection.execute(
                "SELECT * FROM rosemary_states WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            ).fetchone()
            self.connection.execute(
                "INSERT OR IGNORE INTO rosemary_states(guild_id,user_id) VALUES(?,?)",
                (guild_id, user_id),
            )
            state = self.connection.execute(
                "SELECT * FROM rosemary_states WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            ).fetchone()
        if existing is None:
            legacy = self.get_special_condition_consumed(guild_id, "player", user_id)
            if legacy:
                state = self.update_rosemary_state(
                    guild_id, user_id, false_hunger_consumed_total=legacy,
                )
            if self.get_status(guild_id, "player", user_id, "devotion_repressed") is None:
                self.set_status(guild_id, "player", user_id, "devotion_repressed", 1, 1)
        return state

    def update_rosemary_state(self, guild_id: int, user_id: int, **changes):
        allowed = {"seals", "unpacked", "false_hunger_max", "false_hunger_consumed_total", "devotion_max", "haste_pending", "haste_active", "hp_trigger_used", "hunger_coin_active"}
        clean = {key: int(value) for key, value in changes.items() if key in allowed}
        self.get_rosemary_state(guild_id, user_id)
        if clean:
            columns = ",".join(f"{key}=?" for key in clean)
            with self.lock, self.connection:
                self.connection.execute(
                    f"UPDATE rosemary_states SET {columns} WHERE guild_id=? AND user_id=?",
                    (*clean.values(), guild_id, user_id),
                )
        return self.get_rosemary_state(guild_id, user_id)

    def add_rosemary_event(self, guild_id: int, user_id: int, kind: str, message: str, amount=None):
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO rosemary_events(guild_id,user_id,kind,message,amount) VALUES(?,?,?,?,?)",
                (guild_id, user_id, kind[:30], message[:300], amount),
            )

    def record_rosemary_consumption(self, guild_id: int, user_id: int, amount: int):
        state = self.get_rosemary_state(guild_id, user_id)
        total = int(state["false_hunger_consumed_total"]) + max(0, int(amount))
        saved = self.update_rosemary_state(
            guild_id, user_id, false_hunger_consumed_total=total,
        )
        if amount:
            self.add_rosemary_event(guild_id, user_id, "consume", "Falsa Fome consumida", -amount)
        return saved

    def activate_rosemary_hunger_coin_bonus(self, guild_id: int, user_id: int) -> bool:
        """Concede +1 Coin Power até o fim do Encounter uma única vez."""
        state = self.get_rosemary_state(guild_id, user_id)
        if int(state["hunger_coin_active"]):
            return False
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE characters SET coin_power_mod=coin_power_mod+1 WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            )
        self.update_rosemary_state(guild_id, user_id, hunger_coin_active=1)
        self.add_rosemary_event(guild_id, user_id, "hunger", "60 Falsa Fome consumida: +1 Coin Power até o fim do Encounter", 1)
        return True

    def heal_rosemary_profile_hp(self, guild_id: int, user_id: int, percent: int) -> tuple[int, int] | None:
        """A ficha de HP da Rosemary é mantida no perfil persistente do painel."""
        with self.lock, self.connection:
            row = self.connection.execute(
                "SELECT profile_json FROM character_profiles WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            ).fetchone()
            if not row:
                return None
            try:
                profile = json.loads(row["profile_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                return None
            maximum = max(1, int(profile.get("max_hp", profile.get("hp", 1))))
            current = max(0, min(maximum, int(profile.get("hp", maximum))))
            recovered = max(1, (maximum * max(0, int(percent))) // 100)
            profile["hp"] = min(maximum, current + recovered)
            self.connection.execute(
                "UPDATE character_profiles SET profile_json=?,updated_at=CURRENT_TIMESTAMP WHERE guild_id=? AND user_id=?",
                (json.dumps(profile, ensure_ascii=False), guild_id, user_id),
            )
        return profile["hp"], maximum

    def rosemary_uptie(self, guild_id: int, user_id: int) -> int:
        """Lê o Uptie que o painel gravou nas tags da ficha da Rosemary."""
        with self.lock:
            row = self.connection.execute(
                "SELECT tags_json FROM characters WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            ).fetchone()
        try:
            tags = json.loads(row["tags_json"] or "[]") if row else []
        except (TypeError, ValueError, json.JSONDecodeError):
            tags = []
        for tag in tags:
            text = str(tag).casefold().strip()
            if text.startswith("uptie-"):
                try:
                    return max(1, min(5, int(text.split("-", 1)[1])))
                except ValueError:
                    pass
        return 1

    def rosemary_passive_rules(self, guild_id: int, user_id: int) -> dict:
        """Possua-me é U3; contenção, Selos e UNPACK pertencem ao U4."""
        uptie = self.rosemary_uptie(guild_id, user_id)
        if uptie >= 4:
            return {
                "mode": "chains", "uptie": uptie, "devotion": {3: 1, 2: 2, 1: 2, 0: 0},
                "haste_first": 2, "haste_other": 1, "unpack_hunger": 10,
                "unpack_sp": 5, "round_threshold": 30, "round_cost": 10,
                "hp_threshold": 80, "bleed_per": 4, "bleed_damage": 2,
                "bleed_damage_max": 10, "last_bleed": 20, "last_damage": 20,
            }
        if uptie >= 1:
            return {"mode": "hunger", "uptie": uptie}
        return {
            "mode": "none", "uptie": uptie,
        }

    def rosemary_target_is_blood(self, guild_id: int, target_kind: str, target_id: int) -> bool:
        """Bloodfiend/Bloodbag pode vir tanto da tag quanto do nome da ficha."""
        table, identity = ("enemies", "id") if target_kind == "enemy" else ("characters", "user_id")
        with self.lock:
            row = self.connection.execute(
                f"SELECT name,tags_json FROM {table} WHERE guild_id=? AND {identity}=?",
                (guild_id, target_id),
            ).fetchone()
        if not row:
            return False
        try:
            tags = " ".join(str(item) for item in json.loads(row["tags_json"] or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            tags = ""
        target_text = f"{row['name']} {tags}".casefold()
        return "bloodfiend" in target_text or "bloodbag" in target_text

    @staticmethod
    def rosemary_devotion_required(seals: int, rules: dict | None = None) -> int:
        values = (rules or {}).get("devotion", {3: 1, 2: 2, 1: 2, 0: 0})
        return values.get(max(0, min(3, int(seals))), 0)

    def start_rosemary_encounter(self, guild_id: int, user_id: int):
        rules = self.rosemary_passive_rules(guild_id, user_id)
        previous = self.get_rosemary_state(guild_id, user_id)
        if int(previous["hunger_coin_active"]):
            with self.lock, self.connection:
                self.connection.execute(
                    "UPDATE characters SET coin_power_mod=coin_power_mod-1 WHERE guild_id=? AND user_id=?",
                    (guild_id, user_id),
                )
        self.update_rosemary_state(guild_id, user_id, false_hunger_consumed_total=0, hunger_coin_active=0)
        if rules["mode"] != "chains":
            self.add_rosemary_event(guild_id, user_id, "encounter", "Registro de Falsa Fome reiniciado")
            return self.get_rosemary_state(guild_id, user_id)
        self.update_rosemary_state(
            guild_id, user_id, seals=3, unpacked=0, devotion_max=rules["devotion"][3],
            haste_pending=0, haste_active=0, hp_trigger_used=0,
        )
        self.set_status(guild_id, "player", user_id, "devotion_repressed", 1, rules["devotion"][3])
        self.add_rosemary_event(guild_id, user_id, "encounter", f"Contenção iniciada: 3 Selos e {rules['devotion'][3]} Devoção (Uptie {rules['uptie']})")
        return self.get_rosemary_state(guild_id, user_id)

    def resolve_rosemary_unpack(self, guild_id: int, user_id: int, *, force: bool = False, reason: str = "Devoção zerada"):
        rules = self.rosemary_passive_rules(guild_id, user_id)
        if rules["mode"] != "chains":
            return self.get_rosemary_state(guild_id, user_id), False
        state = self.get_rosemary_state(guild_id, user_id)
        devotion = self.get_status(guild_id, "player", user_id, "devotion_repressed")
        if int(state["seals"]) <= 0 or (not force and devotion is not None and devotion.count > 0):
            return state, False
        previous_seals = int(state["seals"])
        seals = max(0, previous_seals - 1)
        unpacked = int(seals == 0)
        next_devotion = self.rosemary_devotion_required(seals, rules)
        haste = rules["haste_first"] if previous_seals == 3 else rules["haste_other"]
        self.set_status(guild_id, "player", user_id, "devotion_repressed", 1, next_devotion)
        hunger = self.get_status(guild_id, "player", user_id, "special_condition")
        maximum = int(state["false_hunger_max"])
        self.set_status(guild_id, "player", user_id, "special_condition", 1, min(maximum, (hunger.count if hunger else 0) + rules["unpack_hunger"]))
        self.change_sp(guild_id, user_id, rules["unpack_sp"])
        saved = self.update_rosemary_state(
            guild_id, user_id, seals=seals, unpacked=unpacked,
            devotion_max=next_devotion, haste_pending=haste,
        )
        message = "UNPACK ativado; kit liberto" if unpacked else f"Selo removido; {seals} restante(s)"
        self.add_rosemary_event(guild_id, user_id, "unpack" if unpacked else "seal", f"{message} • {reason} • Haste {haste} na próxima Rodada", seals)
        return saved, True

    def process_rosemary_round_end(self, guild_id: int, user_id: int):
        rules = self.rosemary_passive_rules(guild_id, user_id)
        if rules["mode"] != "chains":
            return []
        state = self.get_rosemary_state(guild_id, user_id)
        if int(state["seals"]) <= 0:
            self.update_rosemary_state(guild_id, user_id, haste_active=0, haste_pending=0)
            return []
        events = []
        hunger = self.get_status(guild_id, "player", user_id, "special_condition")
        if hunger is not None and hunger.count >= rules["round_threshold"]:
            self.set_status(guild_id, "player", user_id, "special_condition", hunger.potency, hunger.count - rules["round_cost"])
            devotion = self.get_status(guild_id, "player", user_id, "devotion_repressed")
            remaining = max(0, (devotion.count if devotion else 0) - 1)
            self.set_status(guild_id, "player", user_id, "devotion_repressed", 1, remaining)
            self.add_rosemary_event(guild_id, user_id, "round", f"Fim da Rodada: −{rules['round_cost']} Falsa Fome e −1 Devoção", -rules["round_cost"])
            events.append(f"Rosemary consumiu {rules['round_cost']} Falsa Fome e perdeu 1 Devoção")
            _, changed = self.resolve_rosemary_unpack(guild_id, user_id, reason="Fim da Rodada")
            if changed:
                events.append("UNPACK removeu um Selo")
        state = self.get_rosemary_state(guild_id, user_id)
        self.update_rosemary_state(
            guild_id, user_id, haste_active=int(state["haste_pending"]), haste_pending=0,
        )
        return events

    def check_rosemary_hp_trigger(self, guild_id: int, user_id: int, current_hp: int, maximum_hp: int):
        rules = self.rosemary_passive_rules(guild_id, user_id)
        if rules["mode"] != "chains":
            return self.get_rosemary_state(guild_id, user_id), False
        state = self.get_rosemary_state(guild_id, user_id)
        if maximum_hp <= 0 or int(state["seals"]) != 3 or int(state["hp_trigger_used"]):
            return state, False
        if current_hp * 100 >= maximum_hp * rules["hp_threshold"]:
            return state, False
        self.update_rosemary_state(guild_id, user_id, hp_trigger_used=1)
        return self.resolve_rosemary_unpack(guild_id, user_id, force=True, reason=f"HP abaixo de {rules['hp_threshold']}%")

    def list_rosemary_events(self, guild_id: int, user_id: int, limit: int = 20):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM rosemary_events WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT ?",
                (guild_id, user_id, limit),
            ).fetchall()

    def set_charge_potency_mode(
        self, guild_id: int, owner_kind: str, owner_id: int, enabled: bool,
    ) -> None:
        table, key = ("enemies", "id") if owner_kind == "enemy" else ("characters", "user_id")
        if owner_kind not in {"player", "enemy"}:
            raise ValueError("Dono de Charge inválido.")
        with self.lock, self.connection:
            cursor = self.connection.execute(
                f"UPDATE {table} SET charge_potency_enabled=?,charge_spent=0 "
                f"WHERE guild_id=? AND {key}=?",
                (1 if enabled else 0, guild_id, owner_id),
            )
        if not cursor.rowcount:
            raise ValueError("Ficha não encontrada.")

    def get_status(self, guild_id: int, owner_kind: str, owner_id: int, status_type: str) -> CombatStatus | None:
        if status_type not in STATUS_TYPES:
            raise ValueError("Status inválido.")
        with self.lock:
            if owner_kind == "enemy_group_member":
                row = self.connection.execute(
                    "SELECT status_type,potency,count,tremor_type FROM enemy_group_member_statuses WHERE member_id=? AND status_type=?",
                    (owner_id, status_type),
                ).fetchone()
            else:
                row = self.connection.execute(
                    """SELECT status_type,potency,count,tremor_type FROM combat_statuses
                       WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status_type=?""",
                    (guild_id, owner_kind, owner_id, status_type),
                ).fetchone()
        return None if row is None else CombatStatus(
            row["status_type"], row["potency"], row["count"], row["tremor_type"],
        )

    def list_statuses(self, guild_id: int, owner_kind: str, owner_id: int) -> list[CombatStatus]:
        with self.lock:
            rows = self.connection.execute(
                """SELECT status_type,potency,count,tremor_type FROM combat_statuses
                   WHERE guild_id=? AND owner_kind=? AND owner_id=? AND count>0
                   ORDER BY status_type""",
                (guild_id, owner_kind, owner_id),
            ).fetchall()
        return [
            CombatStatus(row["status_type"], row["potency"], row["count"], row["tremor_type"])
            for row in rows
        ]

    def convert_tremor(self, guild_id: int, owner_kind: str, owner_id: int, target: str) -> CombatStatus | None:
        """Amplitude Conversion: troca só o tipo; Potência e Count ficam intactos."""
        if target not in TREMOR_TYPES:
            raise ValueError("Tipo de Tremor inválido.")
        current = self.get_status(guild_id, owner_kind, owner_id, "tremor")
        if current is None or current.count <= 0:
            return None
        with self.lock, self.connection:
            if owner_kind == "enemy_group_member":
                self.connection.execute(
                    "UPDATE enemy_group_member_statuses SET tremor_type=? WHERE member_id=? AND status_type='tremor'",
                    (target, owner_id),
                )
            else:
                self.connection.execute(
                    """UPDATE combat_statuses SET tremor_type=?
                       WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status_type='tremor'""",
                    (target, guild_id, owner_kind, owner_id),
                )
        # Liga/desliga o flag: enquanto o Tremor estiver convertido, TODO Tremor
        # novo — inclusive o de outras fontes — nasce como Scorch.
        if target == "scorch":
            _AMPLITUDE_FLAGS.add((guild_id, owner_kind, owner_id))
        else:
            _AMPLITUDE_FLAGS.discard((guild_id, owner_kind, owner_id))
        return CombatStatus("tremor", current.potency, current.count, target)

    # ---------------------------------------------------------- limite por rodada
    # Conta "N vezes por rodada" (ex.: [Ao Critar] do Imperfect Eye = 2x).
    # Vive só em memória: se o bot reiniciar no meio da rodada o contador zera —
    # inofensivo, e evita criar tabela + migração pra um limite de rodada.
    def consume_effect_round_slot(self, guild_id: int, owner_kind: str, owner_id: int,
                                  key: str, limit: int) -> bool:
        """Gasta 1 uso. True = pode aplicar; False = estourou o limite."""
        if limit <= 0:
            return True
        slot = (guild_id, owner_kind, owner_id, key)
        used = _ROUND_USAGE.get(slot, 0)
        if used >= limit:
            return False
        _ROUND_USAGE[slot] = used + 1
        return True

    def process_round_end_statuses(self, guild_id: int, channel_id: int | None = None):
        """Aplica decaimento do fim da rodada e retorna eventos informativos."""
        for slot in [s for s in _ROUND_USAGE if s[0] == guild_id]:
            _ROUND_USAGE.pop(slot, None)
        events = []
        with self.lock:
            rows = self.connection.execute(
                """SELECT owner_kind,owner_id,status_type,potency,count,tremor_type FROM combat_statuses
                   WHERE guild_id=? AND count>0""", (guild_id,)
            ).fetchall()
            active_owners = None
            if channel_id is not None:
                active_owners = {
                    ("player", row["user_id"])
                    for row in self.connection.execute(
                        """SELECT user_id FROM battle_participants
                           WHERE guild_id=? AND channel_id=?""",
                        (guild_id, channel_id),
                    ).fetchall()
                }
                enemy_names = {
                    row["enemy_name"] for row in self.connection.execute(
                        """SELECT enemy_name FROM battle_field_actions
                           WHERE guild_id=? AND channel_id=?""",
                        (guild_id, channel_id),
                    ).fetchall()
                }
                enemy_names.update(
                    row["target_enemy"] for row in self.connection.execute(
                        """SELECT target_enemy FROM battle_player_actions
                           WHERE guild_id=? AND channel_id=?""",
                        (guild_id, channel_id),
                    ).fetchall()
                )
                for name in enemy_names:
                    enemy = self.connection.execute(
                        "SELECT id FROM enemies WHERE guild_id=? AND name=?",
                        (guild_id, name),
                    ).fetchone()
                    if enemy is not None:
                        active_owners.add(("enemy", enemy["id"]))
        for row in rows:
            if active_owners is not None and (row["owner_kind"], row["owner_id"]) not in active_owners:
                continue
            if row["status_type"] not in STATUS_TYPES:
                # Proteção adicional para um banco que foi alterado por uma
                # versão antiga enquanto o processo atual ainda está aberto.
                with self.lock, self.connection:
                    self.connection.execute(
                        "DELETE FROM combat_statuses WHERE guild_id=? AND owner_kind=? AND owner_id=? AND status_type=?",
                        (guild_id, row["owner_kind"], row["owner_id"], row["status_type"]),
                    )
                continue
            event = on_round_end(CombatStatus(
                row["status_type"], row["potency"], row["count"], row["tremor_type"],
            ))
            if event is None:
                continue
            self.set_status(
                guild_id, row["owner_kind"], row["owner_id"], row["status_type"],
                event.potency_after, event.count_after,
            )
            events.append((row["owner_kind"], row["owner_id"], event))
        return events

    def create_character(self, guild_id: int, user_id: int, name: str) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO characters(guild_id,user_id,name,sp) VALUES(?,?,?,0)
                   ON CONFLICT(guild_id,user_id) DO UPDATE SET name=excluded.name""",
                (guild_id, user_id, name),
            )

    def get_character(self, guild_id: int, user_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM characters WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            ).fetchone()

    def list_characters(self, guild_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM characters WHERE guild_id=? ORDER BY name", (guild_id,)
            ).fetchall()

    def delete_character(self, guild_id: int, user_id: int) -> bool:
        """Remove a ficha e os dados que pertencem exclusivamente a ela."""
        with self.lock, self.connection:
            self.connection.execute(
                "DELETE FROM skills WHERE guild_id=? AND owner_id=?", (guild_id, user_id),
            )
            self.connection.execute(
                "DELETE FROM combat_statuses WHERE guild_id=? AND owner_kind='player' AND owner_id=?",
                (guild_id, user_id),
            )
            self.connection.execute(
                "DELETE FROM profile_appearance WHERE guild_id=? AND owner_kind='player' AND owner_id=?",
                (guild_id, user_id),
            )
            cursor = self.connection.execute(
                "DELETE FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id),
            )
        return bool(cursor.rowcount)

    def transfer_character(self, guild_id: int, old_owner: int, new_owner: int):
        """Move ficha e dependências para outro usuário do mesmo servidor."""
        if old_owner == new_owner:
            raise ValueError("O novo dono precisa ser diferente do dono atual.")
        with self.lock, self.connection:
            source = self.connection.execute(
                "SELECT * FROM characters WHERE guild_id=? AND user_id=?",
                (guild_id, old_owner),
            ).fetchone()
            if source is None:
                raise ValueError("A ficha original não foi encontrada.")
            if self.connection.execute(
                "SELECT 1 FROM characters WHERE guild_id=? AND user_id=?",
                (guild_id, new_owner),
            ).fetchone():
                raise ValueError("O novo dono já possui uma ficha neste servidor.")
            if self.connection.execute(
                """SELECT 1 FROM battle_participants p
                   JOIN battle_sessions b ON b.guild_id=p.guild_id AND b.channel_id=p.channel_id
                   WHERE p.guild_id=? AND p.user_id=? AND b.active=1 LIMIT 1""",
                (guild_id, old_owner),
            ).fetchone():
                raise ValueError("Encerre a batalha ativa antes de transferir esta ficha.")
            for table in ("skills", "combat_statuses", "profile_appearance", "media_upload_jobs"):
                self.connection.execute(
                    f"UPDATE {table} SET owner_id=? WHERE guild_id=? AND owner_id=?"
                    + (" AND owner_kind='player'" if table != "skills" else ""),
                    (new_owner, guild_id, old_owner),
                )
            self.connection.execute(
                "UPDATE characters SET user_id=? WHERE guild_id=? AND user_id=?",
                (new_owner, guild_id, old_owner),
            )
        return self.get_character(guild_id, new_owner)

    def change_sp(self, guild_id: int, user_id: int, delta: int):
        character = self.get_character(guild_id, user_id)
        if character is None:
            return None
        new_sp = clamp_sp(character["sp"] + delta)
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE characters SET sp=? WHERE guild_id=? AND user_id=?",
                (new_sp, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def set_offense_level(self, guild_id: int, user_id: int, offense: int):
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE characters SET offense_level=? WHERE guild_id=? AND user_id=?",
                (offense, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def set_levels(self, guild_id: int, user_id: int, offense: int, defense: int):
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE characters SET offense_level=?, defense_level=? WHERE guild_id=? AND user_id=?",
                (offense, defense, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def add_effects(
        self, guild_id: int, user_id: int, paralysis: int, base: int, coin: int,
        clash: int = 0, offense: int = 0, defense: int = 0,
    ):
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE characters SET paralysis=MAX(0,paralysis+?),
                   base_power_mod=base_power_mod+?, coin_power_mod=coin_power_mod+?,
                   clash_power_mod=clash_power_mod+?, offense_level_mod=offense_level_mod+?,
                   defense_level_mod=defense_level_mod+?
                   WHERE guild_id=? AND user_id=?""",
                (paralysis, base, coin, clash, offense, defense, guild_id, user_id),
            )
        return self.get_character(guild_id, user_id)

    def consume_clash_effects(self, guild_id: int, user_id: int, remaining_paralysis: int) -> None:
        with self.lock, self.connection:
            rosemary = self.connection.execute(
                "SELECT hunger_coin_active FROM rosemary_states WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            ).fetchone()
            hunger_coin = 1 if rosemary and int(rosemary["hunger_coin_active"]) else 0
            self.connection.execute(
                """UPDATE characters SET paralysis=?, coin_power_mod=0,
                   clash_power_mod=0, offense_level_mod=0, defense_level_mod=0
                   WHERE guild_id=? AND user_id=?""",
                (remaining_paralysis, guild_id, user_id),
            )
            if hunger_coin:
                self.connection.execute(
                    "UPDATE characters SET coin_power_mod=1 WHERE guild_id=? AND user_id=?",
                    (guild_id, user_id),
                )

    def save_skill(self, guild_id: int, owner_id: int, skill: Skill) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO skills(guild_id,owner_id,name,base_power,coin_power,coins,unbreakable_coins,description,level_type,effects_json,coin_layout_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(guild_id,owner_id,name) DO UPDATE SET
                   base_power=excluded.base_power, coin_power=excluded.coin_power,
                   coins=excluded.coins, unbreakable_coins=excluded.unbreakable_coins,
                   description=excluded.description, level_type=excluded.level_type,
                   effects_json=excluded.effects_json, coin_layout_json=excluded.coin_layout_json""",
                (guild_id, owner_id, skill.name, skill.base_power, skill.coin_power,
                 skill.coins, skill.unbreakable_coins, skill.description, skill.skill_type,
                _effects_json(skill), _coin_layout_json(skill)),
            )
            current = self.connection.execute("SELECT skill_slot FROM skills WHERE guild_id=? AND owner_id=? AND name=?", (guild_id, owner_id, skill.name)).fetchone()
            if current is not None and not current["skill_slot"]:
                defensive = skill.skill_type in {"guard", "evade", "counter", "clashable_guard", "clashable_counter", "assist_defense", "defense"}
                rows = self.connection.execute("SELECT level_type FROM skills WHERE guild_id=? AND owner_id=? AND name<>?", (guild_id, owner_id, skill.name)).fetchall()
                position = 1 + sum((row["level_type"] in {"guard", "evade", "counter", "clashable_guard", "clashable_counter", "assist_defense", "defense"}) == defensive for row in rows)
                slot = f"d{position}" if defensive else (f"s{position}" if position <= 3 else f"s3-{position-3}")
                self.connection.execute("UPDATE skills SET skill_slot=? WHERE guild_id=? AND owner_id=? AND name=?", (slot, guild_id, owner_id, skill.name))

    def get_skill(self, guild_id: int, owner_id: int, name: str) -> Skill | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM skills WHERE guild_id=? AND owner_id=? AND name=?",
                (guild_id, owner_id, name),
            ).fetchone()
        return None if row is None else Skill(
            row["name"], row["base_power"], row["coin_power"],
            row["coins"], row["description"],
            {"offense": "attack", "defense": "guard"}.get(row["level_type"], row["level_type"]),
            row["unbreakable_coins"], _effects_from_row(row), _coin_layout_from_row(row)
        )

    def list_skills(self, guild_id: int, owner_id: int) -> list[Skill]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM skills WHERE guild_id=? AND owner_id=? ORDER BY name",
                (guild_id, owner_id),
            ).fetchall()
        return [Skill(r["name"], r["base_power"], r["coin_power"], r["coins"], r["description"], {"offense": "attack", "defense": "guard"}.get(r["level_type"], r["level_type"]), r["unbreakable_coins"], _effects_from_row(r), _coin_layout_from_row(r)) for r in rows]

    def delete_skill(self, guild_id: int, owner_id: int, name: str) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM skills WHERE guild_id=? AND owner_id=? AND name=?",
                (guild_id, owner_id, name),
            )
        return cursor.rowcount > 0

    def save_enemy(self, guild_id: int, created_by: int, name: str, sp: int, offense: int, defense: int, uses_sanity: bool = True):
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO enemies(guild_id,name,sp,offense_level,defense_level,uses_sanity,created_by) VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(guild_id,name) DO UPDATE SET
                   sp=excluded.sp, offense_level=excluded.offense_level,
                   defense_level=excluded.defense_level, uses_sanity=excluded.uses_sanity""",
                (guild_id, name, clamp_sp(sp), offense, defense, int(uses_sanity), created_by),
            )
        return self.get_enemy(guild_id, name)

    def get_enemy(self, guild_id: int, name: str):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM enemies WHERE guild_id=? AND name=?", (guild_id, name)
            ).fetchone()

    def get_enemy_by_id(self, enemy_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM enemies WHERE id=?", (enemy_id,)
            ).fetchone()

    def list_enemies(self, guild_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM enemies WHERE guild_id=? ORDER BY name", (guild_id,)
            ).fetchall()

    def create_enemy_group(self, guild_id: int, template_enemy_id: int, name: str, quantity: int, hp_max: int) -> list:
        """Cria instâncias independentes que compartilham a ficha-base e as Skills."""
        quantity = max(1, min(20, int(quantity)))
        hp_max = max(1, int(hp_max))
        with self.lock, self.connection:
            template = self.connection.execute(
                "SELECT id,name,sp FROM enemies WHERE guild_id=? AND id=?", (guild_id, template_enemy_id),
            ).fetchone()
            if template is None:
                raise ValueError("Ficha-base de hostil não encontrada.")
            cursor = self.connection.execute(
                "INSERT INTO enemy_groups(guild_id,name,template_enemy_id) VALUES(?,?,?)",
                (guild_id, name[:80], template_enemy_id),
            )
            group_id = int(cursor.lastrowid)
            self.connection.executemany(
                """INSERT INTO enemy_group_members(group_id,member_name,hp,hp_max,sp)
                   VALUES(?,?,?,?,?)""",
                [(group_id, f"{template['name']} {index}", hp_max, hp_max, template["sp"]) for index in range(1, quantity + 1)],
            )
            return self.connection.execute(
                "SELECT * FROM enemy_group_members WHERE group_id=? ORDER BY id", (group_id,)
            ).fetchall()

    def get_enemy_group_member_combatant(self, guild_id: int, member_id: int):
        """Ficha de combate individual: atributos/skills do molde e recursos do integrante."""
        with self.lock:
            row = self.connection.execute(
                """SELECT e.*,m.id AS group_member_id,m.member_name,m.hp AS member_hp,
                          m.hp_max AS member_hp_max,m.sp AS member_sp,
                          m.paralysis AS member_paralysis,m.base_power_mod AS member_base_power_mod,
                          m.coin_power_mod AS member_coin_power_mod,m.clash_power_mod AS member_clash_power_mod,
                          m.offense_level_mod AS member_offense_level_mod,m.defense_level_mod AS member_defense_level_mod,
                          g.id AS group_id,g.name AS group_name
                   FROM enemy_group_members m
                   JOIN enemy_groups g ON g.id=m.group_id
                   JOIN enemies e ON e.id=g.template_enemy_id
                   WHERE g.guild_id=? AND m.id=?""", (guild_id, member_id),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result.update({
            "id": int(row["id"]), "name": row["member_name"], "sp": int(row["member_sp"]),
            "hp": int(row["member_hp"]), "hp_max": int(row["member_hp_max"]),
            "paralysis": int(row["member_paralysis"]), "base_power_mod": int(row["member_base_power_mod"]),
            "coin_power_mod": int(row["member_coin_power_mod"]), "clash_power_mod": int(row["member_clash_power_mod"]),
            "offense_level_mod": int(row["member_offense_level_mod"]), "defense_level_mod": int(row["member_defense_level_mod"]),
        })
        return result

    def update_enemy_group_member_combat(self, guild_id: int, member_id: int, *, sp: int, paralysis: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE enemy_group_members SET sp=?,paralysis=?,
                   coin_power_mod=0,clash_power_mod=0,offense_level_mod=0,defense_level_mod=0
                   WHERE id=? AND group_id IN (SELECT id FROM enemy_groups WHERE guild_id=?)""",
                (max(-45, min(45, int(sp))), max(0, int(paralysis)), member_id, guild_id),
            )

    def list_enemy_groups(self, guild_id: int):
        with self.lock:
            return self.connection.execute(
                """SELECT g.id,g.name,g.template_enemy_id,e.name AS template_name,
                          COUNT(m.id) AS member_count
                   FROM enemy_groups g JOIN enemies e ON e.id=g.template_enemy_id
                   LEFT JOIN enemy_group_members m ON m.group_id=g.id
                   WHERE g.guild_id=? GROUP BY g.id ORDER BY g.name""",
                (guild_id,),
            ).fetchall()

    def list_enemy_group_members(self, group_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM enemy_group_members WHERE group_id=? ORDER BY id", (group_id,)
            ).fetchall()

    def get_enemy_group(self, guild_id: int, group_id: int):
        with self.lock:
            return self.connection.execute(
                """SELECT g.*,e.name AS template_name,e.offense_level,e.defense_level,e.uses_sanity
                   FROM enemy_groups g JOIN enemies e ON e.id=g.template_enemy_id
                   WHERE g.guild_id=? AND g.id=?""", (guild_id, group_id),
            ).fetchone()

    def get_guild_settings(self, guild_id: int) -> dict:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)
            ).fetchone()
            if row is None:
                return {"guild_id": str(guild_id), "audit_channel_id": "0", "clash_channel_id": "0"}
            columns = {r[1] for r in self.connection.execute("PRAGMA table_info(guild_settings)")}
            return {
                "guild_id": str(row["guild_id"]),
                "audit_channel_id": str(row["audit_channel_id"] or 0),
                "clash_channel_id": str(row["clash_channel_id"] or 0) if "clash_channel_id" in columns else "0",
            }

    def set_guild_settings(self, guild_id: int, settings: dict) -> dict:
        with self.lock, self.connection:
            row = self.connection.execute(
                "SELECT audit_channel_id, clash_channel_id FROM guild_settings WHERE guild_id=?",
                (guild_id,),
            ).fetchone()
            keep_audit = int(row["audit_channel_id"] or 0) if row else 0
            keep_arena = int(row["clash_channel_id"] or 0) if row else 0
            if "audit_channel_id" in settings:
                raw_channel = str(settings.get("audit_channel_id", "0") or "0").strip()
                audit_channel_id = int(raw_channel) if raw_channel.isdigit() else 0
            else:
                audit_channel_id = keep_audit
            if "clash_channel_id" in settings:
                raw_arena = str(settings.get("clash_channel_id", "0") or "0").strip()
                clash_channel_id = int(raw_arena) if raw_arena.isdigit() else 0
            else:
                clash_channel_id = keep_arena
            self.connection.execute(
                """INSERT INTO guild_settings(guild_id, audit_channel_id, clash_channel_id, updated_at)
                   VALUES(?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(guild_id) DO UPDATE SET
                   audit_channel_id=excluded.audit_channel_id,
                   clash_channel_id=excluded.clash_channel_id,
                   updated_at=CURRENT_TIMESTAMP""",
                (guild_id, audit_channel_id, clash_channel_id)
            )
        return self.get_guild_settings(guild_id)

    def add_enemy_group_members(self, guild_id: int, group_id: int, quantity: int) -> list:
        quantity = max(1, min(20, int(quantity)))
        with self.lock, self.connection:
            group = self.connection.execute(
                """SELECT g.*,e.name AS template_name
                   FROM enemy_groups g JOIN enemies e ON e.id=g.template_enemy_id
                   WHERE g.guild_id=? AND g.id=?""",
                (guild_id, group_id),
            ).fetchone()
            if group is None:
                raise ValueError("Grupo não encontrado.")
            last = self.connection.execute(
                "SELECT COUNT(*) AS total FROM enemy_group_members WHERE group_id=?", (group_id,)
            ).fetchone()["total"]
            sample = self.connection.execute(
                "SELECT hp_max,sp FROM enemy_group_members WHERE group_id=? ORDER BY id LIMIT 1", (group_id,)
            ).fetchone()
            hp_max = int(sample["hp_max"]) if sample else 100
            sp = int(sample["sp"]) if sample else 0
            self.connection.executemany(
                "INSERT INTO enemy_group_members(group_id,member_name,hp,hp_max,sp) VALUES(?,?,?,?,?)",
                [(group_id, f"{group['template_name']} {last + index}", hp_max, hp_max, sp) for index in range(1, quantity + 1)],
            )
            return self.connection.execute(
                "SELECT * FROM enemy_group_members WHERE group_id=? ORDER BY id", (group_id,)
            ).fetchall()

    def update_enemy_group_member(self, guild_id: int, member_id: int, values: dict):
        allowed = {"member_name", "hp", "hp_max", "sp", "paralysis", "base_power_mod", "coin_power_mod", "clash_power_mod", "offense_level_mod", "defense_level_mod"}
        fields = {key: values[key] for key in allowed if key in values}
        if not fields:
            raise ValueError("Nenhum valor para atualizar.")
        if "hp_max" in fields: fields["hp_max"] = max(1, int(fields["hp_max"]))
        if "hp" in fields: fields["hp"] = max(0, int(fields["hp"]))
        if "sp" in fields: fields["sp"] = max(-45, min(45, int(fields["sp"])))
        if "member_name" in fields: fields["member_name"] = str(fields["member_name"]).strip()[:80]
        assignments = ",".join(f"{key}=?" for key in fields)
        with self.lock, self.connection:
            cursor = self.connection.execute(
                f"""UPDATE enemy_group_members SET {assignments}
                    WHERE id=? AND group_id IN (SELECT id FROM enemy_groups WHERE guild_id=?)""",
                (*fields.values(), member_id, guild_id),
            )
            if not cursor.rowcount: raise ValueError("Integrante não encontrado.")
            return self.connection.execute("SELECT * FROM enemy_group_members WHERE id=?", (member_id,)).fetchone()

    def list_enemy_group_member_statuses(self, member_id: int):
        with self.lock:
            return self.connection.execute("SELECT status_type,potency,count,tremor_type FROM enemy_group_member_statuses WHERE member_id=? ORDER BY status_type", (member_id,)).fetchall()

    def save_enemy_group_member_statuses(self, guild_id: int, member_id: int, statuses: list[dict]):
        if not isinstance(statuses, list) or len(statuses) > 30: raise ValueError("Lista de efeitos inválida.")
        with self.lock, self.connection:
            exists = self.connection.execute("SELECT 1 FROM enemy_group_members m JOIN enemy_groups g ON g.id=m.group_id WHERE m.id=? AND g.guild_id=?", (member_id, guild_id)).fetchone()
            if not exists: raise ValueError("Integrante não encontrado.")
            # O editor não conhece Amplitude Conversion: o tipo já convertido do
            # Tremor é preservado, a menos que o cliente envie outro tipo válido.
            stored = self.connection.execute(
                "SELECT tremor_type FROM enemy_group_member_statuses WHERE member_id=? AND status_type='tremor'",
                (member_id,),
            ).fetchone()
            preserved_tremor = stored["tremor_type"] if stored else "normal"
            self.connection.execute("DELETE FROM enemy_group_member_statuses WHERE member_id=?", (member_id,))
            for item in statuses:
                status = re.sub(r"[^a-z0-9_]", "", str(item.get("status_type", "")).lower())[:40]
                potency, count = max(0, int(item.get("potency", 0))), max(0, int(item.get("count", 0)))
                requested = str(item.get("tremor_type", "") or "")
                tremor_type = (requested if requested in TREMOR_TYPES else preserved_tremor) if status == "tremor" else "normal"
                if status and count: self.connection.execute("INSERT INTO enemy_group_member_statuses(member_id,status_type,potency,count,tremor_type) VALUES(?,?,?,?,?)", (member_id,status,potency,count,tremor_type))
            return self.list_enemy_group_member_statuses(member_id)

    def remove_enemy_group_member(self, guild_id: int, member_id: int) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM enemy_group_members WHERE id=? AND group_id IN (SELECT id FROM enemy_groups WHERE guild_id=?)",
                (member_id, guild_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _normalize_enemy_tags(tags) -> list[str]:
        """Normaliza tags livres sem transformar texto do mestre em SQL/Markdown."""
        if isinstance(tags, str):
            tags = tags.split(",")
        result: list[str] = []
        seen: set[str] = set()
        for raw in tags or []:
            tag = " ".join(str(raw).strip().split())[:32]
            key = tag.casefold()
            if not tag or key in seen:
                continue
            seen.add(key)
            result.append(tag)
            if len(result) == 12:
                break
        return result

    def get_enemy_tags(self, enemy_id: int) -> list[str]:
        with self.lock:
            row = self.connection.execute(
                "SELECT tags_json FROM enemies WHERE id=?", (enemy_id,)
            ).fetchone()
        if row is None:
            return []
        try:
            return self._normalize_enemy_tags(json.loads(row["tags_json"] or "[]"))
        except (TypeError, json.JSONDecodeError):
            return []

    def set_enemy_tags(self, guild_id: int, enemy_id: int, tags) -> list[str]:
        normalized = self._normalize_enemy_tags(tags)
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "UPDATE enemies SET tags_json=? WHERE guild_id=? AND id=?",
                (json.dumps(normalized, ensure_ascii=False), guild_id, enemy_id),
            )
        if not cursor.rowcount:
            raise ValueError("Inimigo não encontrado.")
        return normalized

    def delete_enemy(self, guild_id: int, name: str) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM enemies WHERE guild_id=? AND name=?", (guild_id, name)
            )
        return cursor.rowcount > 0

    def change_enemy_sp(self, enemy_id: int, delta: int):
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE enemies SET sp=MAX(-45,MIN(45,sp+?)) WHERE id=?", (delta, enemy_id)
            )
            return self.connection.execute("SELECT * FROM enemies WHERE id=?", (enemy_id,)).fetchone()

    def add_enemy_effects(
        self, enemy_id: int, paralysis: int, base: int, coin: int,
        clash: int, offense: int, defense: int = 0,
    ):
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE enemies SET paralysis=MAX(0,paralysis+?),
                   base_power_mod=base_power_mod+?, coin_power_mod=coin_power_mod+?,
                   clash_power_mod=clash_power_mod+?, offense_level_mod=offense_level_mod+?,
                   defense_level_mod=defense_level_mod+?
                   WHERE id=?""",
                (paralysis, base, coin, clash, offense, defense, enemy_id),
            )
            return self.connection.execute("SELECT * FROM enemies WHERE id=?", (enemy_id,)).fetchone()

    def consume_enemy_effects(self, enemy_id: int, remaining_paralysis: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE enemies SET paralysis=?, coin_power_mod=0,
                   clash_power_mod=0, offense_level_mod=0, defense_level_mod=0 WHERE id=?""",
                (remaining_paralysis, enemy_id),
            )

    def save_enemy_skill(self, enemy_id: int, skill: Skill) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO enemy_skills(enemy_id,name,base_power,coin_power,coins,unbreakable_coins,description,skill_type,effects_json,coin_layout_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(enemy_id,name) DO UPDATE SET
                   base_power=excluded.base_power, coin_power=excluded.coin_power,
                   coins=excluded.coins, unbreakable_coins=excluded.unbreakable_coins,
                   description=excluded.description, skill_type=excluded.skill_type,
                   effects_json=excluded.effects_json, coin_layout_json=excluded.coin_layout_json""",
                (enemy_id, skill.name, skill.base_power, skill.coin_power, skill.coins,
                 skill.unbreakable_coins, skill.description, skill.skill_type,
                 _effects_json(skill), _coin_layout_json(skill)),
            )
            current = self.connection.execute("SELECT skill_slot FROM enemy_skills WHERE enemy_id=? AND name=?", (enemy_id, skill.name)).fetchone()
            if current is not None and not current["skill_slot"]:
                defensive = skill.skill_type in {"guard", "evade", "counter", "clashable_guard", "clashable_counter", "assist_defense", "defense"}
                rows = self.connection.execute("SELECT skill_type FROM enemy_skills WHERE enemy_id=? AND name<>?", (enemy_id, skill.name)).fetchall()
                position = 1 + sum((row["skill_type"] in {"guard", "evade", "counter", "clashable_guard", "clashable_counter", "assist_defense", "defense"}) == defensive for row in rows)
                slot = f"d{position}" if defensive else (f"s{position}" if position <= 3 else f"s3-{position-3}")
                self.connection.execute("UPDATE enemy_skills SET skill_slot=? WHERE enemy_id=? AND name=?", (slot, enemy_id, skill.name))

    def get_enemy_skill(self, enemy_id: int, name: str) -> Skill | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM enemy_skills WHERE enemy_id=? AND name=?", (enemy_id, name)
            ).fetchone()
        return None if row is None else Skill(
            row["name"], row["base_power"], row["coin_power"], row["coins"], row["description"], row["skill_type"], row["unbreakable_coins"], _effects_from_row(row), _coin_layout_from_row(row)
        )

    def list_enemy_skills(self, enemy_id: int) -> list[Skill]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM enemy_skills WHERE enemy_id=? ORDER BY name", (enemy_id,)
            ).fetchall()
        return [Skill(r["name"], r["base_power"], r["coin_power"], r["coins"], r["description"], r["skill_type"], r["unbreakable_coins"], _effects_from_row(r), _coin_layout_from_row(r)) for r in rows]

    def delete_enemy_skill(self, enemy_id: int, name: str) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM enemy_skills WHERE enemy_id=? AND name=?", (enemy_id, name)
            )
        return cursor.rowcount > 0

    def start_battle(self, guild_id: int, channel_id: int, name: str, created_by: int):
        with self.lock, self.connection:
            # Contadores de consumo pertencem somente ao encontro atual.
            self.connection.execute(
                "UPDATE characters SET charge_spent=0,special_condition_consumed=0 WHERE guild_id=?", (guild_id,),
            )
            self.connection.execute(
                "UPDATE enemies SET charge_spent=0,special_condition_consumed=0 WHERE guild_id=?", (guild_id,),
            )
            self.connection.execute(
                "DELETE FROM battle_field_actions WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "DELETE FROM battle_player_actions WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "DELETE FROM battle_participants WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                """INSERT INTO battle_sessions(guild_id,channel_id,name,turn,created_by,active,phase)
                   VALUES(?,?,?,1,?,1,'preparation')
                   ON CONFLICT(guild_id,channel_id) DO UPDATE SET
                   name=excluded.name, turn=1, created_by=excluded.created_by,
                   active=1, panel_message_id=NULL, phase='preparation'""",
                (guild_id, channel_id, name, created_by),
            )
        return self.get_battle(guild_id, channel_id)

    def get_battle(self, guild_id: int, channel_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM battle_sessions WHERE guild_id=? AND channel_id=? AND active=1",
                (guild_id, channel_id),
            ).fetchone()

    def set_battle_panel_message(self, guild_id: int, channel_id: int, message_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE battle_sessions SET panel_message_id=? WHERE guild_id=? AND channel_id=?",
                (message_id, guild_id, channel_id),
            )

    def end_battle(self, guild_id: int, channel_id: int) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "UPDATE battle_sessions SET active=0 WHERE guild_id=? AND channel_id=? AND active=1",
                (guild_id, channel_id),
            )
        return cursor.rowcount > 0

    def add_field_action(self, guild_id: int, channel_id: int, enemy_name: str, enemy_skill: str, target_user_id: int | None = None, enemy_group_member_id: int | None = None):
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """INSERT INTO battle_field_actions(guild_id,channel_id,enemy_name,enemy_skill,target_user_id,enemy_group_member_id)
                   VALUES(?,?,?,?,?,?)""",
                (guild_id, channel_id, enemy_name, enemy_skill, target_user_id, enemy_group_member_id),
            )
            return self.connection.execute(
                "SELECT * FROM battle_field_actions WHERE id=?", (cursor.lastrowid,)
            ).fetchone()

    def add_player_action(
        self, guild_id: int, channel_id: int, user_id: int, character_name: str,
        target_enemy: str, player_skill: str, action_type: str, final_damage: int,
    ):
        if action_type not in {"unopposed", "follow_up"}:
            raise ValueError("Tipo de ação do jogador inválido")
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """INSERT INTO battle_player_actions(
                       guild_id,channel_id,user_id,character_name,target_enemy,
                       player_skill,action_type,final_damage
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (guild_id, channel_id, user_id, character_name, target_enemy,
                 player_skill, action_type, final_damage),
            )
            return self.connection.execute(
                "SELECT * FROM battle_player_actions WHERE id=?", (cursor.lastrowid,)
            ).fetchone()

    def add_enemy_free_action(self, guild_id: int, channel_id: int, enemy_id: int, enemy_skill: str, target_user_id: int, variant: str = "unopposed", enemy_group_member_id: int | None = None):
        if variant not in {"unopposed", "follow_up"}:
            raise ValueError("Variação de ataque livre inválida")
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """INSERT INTO battle_enemy_free_actions(guild_id,channel_id,enemy_id,enemy_group_member_id,enemy_skill,target_user_id,variant)
                   VALUES(?,?,?,?,?,?,?)""", (guild_id, channel_id, enemy_id, enemy_group_member_id, enemy_skill, target_user_id, variant),
            )
            return self.connection.execute("SELECT * FROM battle_enemy_free_actions WHERE id=?", (cursor.lastrowid,)).fetchone()

    def list_enemy_free_actions(self, guild_id: int, channel_id: int, status: str | None = None):
        query, params = "SELECT * FROM battle_enemy_free_actions WHERE guild_id=? AND channel_id=?", [guild_id, channel_id]
        if status is not None: query += " AND status=?"; params.append(status)
        query += " ORDER BY id"
        with self.lock: return self.connection.execute(query, params).fetchall()

    def resolve_enemy_free_action(self, action_id: int, final_damage: int) -> None:
        with self.lock, self.connection:
            self.connection.execute("UPDATE battle_enemy_free_actions SET status='resolved',final_damage=? WHERE id=?", (final_damage, action_id))

    def list_player_actions(self, guild_id: int, channel_id: int):
        with self.lock:
            return self.connection.execute(
                """SELECT * FROM battle_player_actions
                   WHERE guild_id=? AND channel_id=? ORDER BY id""",
                (guild_id, channel_id),
            ).fetchall()

    def list_field_actions(self, guild_id: int, channel_id: int, status: str | None = None):
        query = "SELECT * FROM battle_field_actions WHERE guild_id=? AND channel_id=?"
        params: list[object] = [guild_id, channel_id]
        if status is not None:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY id"
        with self.lock:
            return self.connection.execute(query, params).fetchall()

    def get_field_action(self, action_id: int):
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM battle_field_actions WHERE id=?", (action_id,)
            ).fetchone()

    def claim_field_action(self, action_id: int, user_id: int, player_skill: str) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """UPDATE battle_field_actions
                   SET status='claimed', claimed_by=?, player_skill=?
                   WHERE id=? AND status='open'""",
                (user_id, player_skill, action_id),
            )
        return cursor.rowcount > 0

    def resolve_field_action(self, action_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE battle_field_actions SET status='resolved' WHERE id=?", (action_id,)
            )

    def release_field_action(self, action_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE battle_field_actions
                   SET status='open', claimed_by=NULL, player_skill=NULL WHERE id=?""",
                (action_id,),
            )

    def next_battle_turn(self, guild_id: int, channel_id: int):
        # `[Fim da Rodada]` dispara aqui, **antes** do decaimento e antes de o
        # turno virar — assim o gift vê a rodada que está acabando, e não a
        # próxima. O `[Início da Rodada]` correspondente sai em
        # `set_battle_phase("declaration")`.
        self.fire_session(guild_id, channel_id, "session_round_end", self.current_turn(guild_id, channel_id))
        self.last_round_status_events = self.process_round_end_statuses(guild_id, channel_id)
        with self.lock:
            rosemary_players = self.connection.execute(
                """SELECT r.user_id FROM rosemary_states r
                   JOIN battle_participants p ON p.guild_id=r.guild_id AND p.user_id=r.user_id
                   WHERE p.guild_id=? AND p.channel_id=?""",
                (guild_id, channel_id),
            ).fetchall()
        for player in rosemary_players:
            self.last_round_status_events.extend(
                self.process_rosemary_round_end(guild_id, int(player["user_id"]))
            )
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE battle_sessions SET turn=turn+1 WHERE guild_id=? AND channel_id=? AND active=1",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "DELETE FROM battle_field_actions WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "DELETE FROM battle_player_actions WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "UPDATE battle_participants SET status='waiting', ready=0 WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
            self.connection.execute(
                "UPDATE battle_sessions SET phase='preparation' WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
        return self.get_battle(guild_id, channel_id)

    def join_battle(self, guild_id: int, channel_id: int, user_id: int, character_name: str):
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO battle_participants(guild_id,channel_id,user_id,character_name,status)
                   VALUES(?,?,?,?, 'waiting')
                   ON CONFLICT(guild_id,channel_id,user_id) DO UPDATE SET
                   character_name=excluded.character_name""",
                (guild_id, channel_id, user_id, character_name),
            )
        return self.get_battle_participant(guild_id, channel_id, user_id)

    def leave_battle(self, guild_id: int, channel_id: int, user_id: int) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM battle_participants WHERE guild_id=? AND channel_id=? AND user_id=?",
                (guild_id, channel_id, user_id),
            )
        return cursor.rowcount > 0

    def get_battle_participant(self, guild_id: int, channel_id: int, user_id: int):
        with self.lock:
            return self.connection.execute(
                """SELECT * FROM battle_participants
                   WHERE guild_id=? AND channel_id=? AND user_id=?""",
                (guild_id, channel_id, user_id),
            ).fetchone()

    def list_battle_participants(self, guild_id: int, channel_id: int):
        with self.lock:
            return self.connection.execute(
                """SELECT * FROM battle_participants
                   WHERE guild_id=? AND channel_id=? ORDER BY joined_at, user_id""",
                (guild_id, channel_id),
            ).fetchall()

    def set_battle_participant_status(
        self, guild_id: int, channel_id: int, user_id: int, status: str,
    ) -> None:
        if status not in {"waiting", "clashing", "done"}:
            raise ValueError("Status de participante inválido")
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE battle_participants SET status=?
                   WHERE guild_id=? AND channel_id=? AND user_id=?""",
                (status, guild_id, channel_id, user_id),
            )

    # --- PASSIVAS ---
    def list_passives(self, guild_id: int, owner_kind: str, owner_id: int) -> list[dict]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM passives WHERE guild_id=? AND owner_kind=? AND owner_id=? ORDER BY id",
                (guild_id, owner_kind, owner_id),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_passive(self, guild_id: int, owner_kind: str, owner_id: int, name: str, description: str, effects_json: str = "[]", passive_id: int | None = None) -> dict:
        with self.lock, self.connection:
            if passive_id:
                self.connection.execute(
                    "UPDATE passives SET name=?, description=?, effects_json=? WHERE id=? AND guild_id=? AND owner_kind=? AND owner_id=?",
                    (name, description, effects_json, passive_id, guild_id, owner_kind, owner_id),
                )
            else:
                cursor = self.connection.execute(
                    "INSERT INTO passives (guild_id, owner_kind, owner_id, name, description, effects_json) VALUES (?,?,?,?,?,?)",
                    (guild_id, owner_kind, owner_id, name, description, effects_json),
                )
                passive_id = cursor.lastrowid
            return {"id": passive_id, "name": name, "description": description}

    def delete_passive(self, guild_id: int, owner_kind: str, owner_id: int, passive_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "DELETE FROM passives WHERE id=? AND guild_id=? AND owner_kind=? AND owner_id=?",
                (passive_id, guild_id, owner_kind, owner_id),
            )

    # --- E.G.O GIFTS ---
    def list_ego_gifts(self, guild_id: int, owner_kind: str, owner_id: int) -> list[dict]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM ego_gifts WHERE guild_id=? AND owner_kind=? AND owner_id=? ORDER BY tier DESC, id",
                (guild_id, owner_kind, owner_id),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_active_ego_gift_effects(
        self, guild_id: int, owner_kind: str, owner_id: int,
    ) -> list[tuple[str, tuple[SkillEffect, ...], str]]:
        """Cláusulas (``effects_json``) dos gifts **ativos** desta ficha.

        Devolve ``(nome, efeitos, tag_da_facao)`` — quem chama precisa do nome
        para marcar a origem no log, senão o efeito do gift se passaria por
        efeito de skill, e precisa da ``active_tag`` para resolver o
        ``effect_owner="faction"`` (*"todos os aliados da Middle"*).
        Reusa ``_effects_from_row`` (que já cuida do alias ``false_hunger`` e
        falha devolvendo tupla vazia em vez de estourar no meio do combate).
        O **bloco 7** (``active_*``) é filtrado aqui: um gift que a ficha não
        habilitou simplesmente não aparece — nenhum call site muda.
        """
        with self.lock:
            rows = self.connection.execute(
                """SELECT * FROM ego_gifts
                   WHERE guild_id=? AND owner_kind=? AND owner_id=? AND is_active=1
                   ORDER BY tier DESC, id""",
                (guild_id, owner_kind, owner_id),
            ).fetchall()
        # Keywords só são lidas se algum gift tiver gate: hoje a maioria não
        # tem, e essa chamada custaria uma query por disparo à toa.
        has_gate = any(
            "active_status" in row.keys()
            and (str(row["active_status"] or "").strip() or str(row["active_tag"] or "").strip())
            for row in rows
        )
        owner_keywords = self.get_keywords(guild_id, owner_kind, owner_id) if has_gate else frozenset()
        ally_cache: dict[str, int] = {}

        def count_allies(tag: str) -> int:
            if tag not in ally_cache:
                ally_cache[tag] = self.count_allies_with(guild_id, owner_kind, owner_id, tag)
            return ally_cache[tag]

        sources: list[tuple[str, tuple[SkillEffect, ...], str]] = []
        for row in rows:
            if not _gift_gate_ok(row, owner_keywords, count_allies):
                continue
            effects = _effects_from_row(row)
            if effects:
                sources.append((row["name"], effects, str(row["active_tag"] or "")))
        return sources

    def get_keywords(self, guild_id: int, owner_kind: str, owner_id: int) -> frozenset[str]:
        """Keywords da ficha (§7.3) — lista que o mestre marca no Control Center."""
        table = "characters" if owner_kind == "player" else "enemies"
        key = "user_id" if owner_kind == "player" else "id"
        with self.lock:
            row = self.connection.execute(
                f"SELECT keywords FROM {table} WHERE guild_id=? AND {key}=?",
                (guild_id, owner_id),
            ).fetchone()
        return normalize_keywords(None if row is None else row["keywords"])

    def set_keywords(self, guild_id: int, owner_kind: str, owner_id: int, keywords) -> frozenset[str]:
        table = "characters" if owner_kind == "player" else "enemies"
        key = "user_id" if owner_kind == "player" else "id"
        cleaned = sorted(normalize_keywords(keywords))
        with self.lock, self.connection:
            self.connection.execute(
                f"UPDATE {table} SET keywords=? WHERE guild_id=? AND {key}=?",
                (json.dumps(cleaned, ensure_ascii=False), guild_id, owner_id),
            )
        return frozenset(cleaned)

    def shared_bloodfeast_consumed(self, guild_id: int, owner_kind: str, owner_id: int) -> int:
        """Bloodfeast **Consumido (Compartilhado)** — a soma do time inteiro.

        A print do The Family's Resentment diz *"cada 50 Bloodfeast Consumido
        (Compartilhado)"*. O `(Compartilhado)` é o que faz a diferença:
        `bloodfeast_consumed` sozinho é **por ficha**, e dois aliados
        consumindo 30 cada dariam 30 — quando a regra é 50.

        "Aliado" = todos os sinners do encontro, **o próprio incluído**
        (mesma definição de `encounter_member_ids`).
        """
        membros = self.encounter_member_ids(guild_id, owner_kind, owner_id)
        if owner_kind == "player":
            if not membros:
                return 0
            marcas = ",".join("?" * len(membros))
            with self.lock:
                linha = self.connection.execute(
                    f"SELECT COALESCE(SUM(COALESCE(bloodfeast_consumed,0)),0) "
                    f"FROM characters WHERE guild_id=? AND user_id IN ({marcas})",
                    (guild_id, *membros),
                ).fetchone()
            return int(linha[0] or 0)
        if not membros:
            return self.get_resource_consumed(guild_id, owner_kind, owner_id, "bloodfeast")
        marcas = ",".join("?" * len(membros))
        with self.lock:
            linha = self.connection.execute(
                f"SELECT COALESCE(SUM(COALESCE(bloodfeast_consumed,0)),0) "
                f"FROM enemies WHERE guild_id=? AND id IN ({marcas})",
                (guild_id, *membros),
            ).fetchone()
        return int(linha[0] or 0)

    def encounter_member_ids(self, guild_id: int, owner_kind: str, owner_id: int) -> set[int]:
        """Quem conta como sinner do encontro — **o próprio incluído**.

        O Limbus escreve "aliados" com visão de time, e o time inclui quem está
        jogando: *"3 ou mais aliados da Middle"* é **3 no total**, o dono
        contando. Com batalha ativa o encontro é o painel dela; sem batalha, é
        o grupo do servidor — o que dá para saber sem sessão aberta.
        """
        table = "characters" if owner_kind == "player" else "enemies"
        key = "user_id" if owner_kind == "player" else "id"
        with self.lock:
            battle = None
            if owner_kind == "player":
                battle = self.connection.execute(
                    """SELECT p.channel_id FROM battle_participants p
                       JOIN battle_sessions s
                         ON s.guild_id = p.guild_id AND s.channel_id = p.channel_id
                       WHERE p.guild_id=? AND p.user_id=? AND s.active=1
                       ORDER BY p.channel_id DESC LIMIT 1""",
                    (guild_id, owner_id),
                ).fetchone()
            if battle is None:
                rows = self.connection.execute(
                    f"SELECT {key} AS member FROM {table} WHERE guild_id=?",
                    (guild_id,),
                ).fetchall()
            else:
                rows = self.connection.execute(
                    """SELECT user_id AS member FROM battle_participants
                       WHERE guild_id=? AND channel_id=?""",
                    (guild_id, battle["channel_id"]),
                ).fetchall()
        # O `| owner_id` cobre a ficha que ainda não tem linha na tabela: ela
        # conta como um sinner do encontro mesmo assim.
        return {row["member"] for row in rows} | {owner_id}

    # ─────────────────────────── Etapa 5: duração e limite dos gifts ──────
    def reserve_gift_activation(
        self, guild_id: int, owner_kind: str, owner_id: int,
        gift_name: str, window_key: str, limit: int | None,
    ) -> bool:
        """Gasta 1 ativação do limite. ``False`` = a cláusula não pode disparar.

        ``limit`` 0/None = sem limite, e o contador nem é criado. A linha
        contadora usa ``effect_type=''`` para não se misturar com efeito
        pendente nenhum.
        """
        if not limit:
            return True
        with self.lock, self.connection:
            row = self.connection.execute(
                """SELECT id,activations_left FROM ego_gift_state
                   WHERE guild_id=? AND owner_kind=? AND owner_id=?
                   AND gift_name=? AND effect_type='' AND window_key=?""",
                (guild_id, owner_kind, owner_id, gift_name, window_key),
            ).fetchone()
            if row is None:
                self.connection.execute(
                    """INSERT INTO ego_gift_state
                       (guild_id,owner_kind,owner_id,gift_name,effect_type,window_key,activations_left)
                       VALUES (?,?,?,?,'',?,?)""",
                    (guild_id, owner_kind, owner_id, gift_name, window_key, limit - 1),
                )
                return True
            left = row["activations_left"]
            if left is None or left <= 0:
                return False
            self.connection.execute(
                "UPDATE ego_gift_state SET activations_left=? WHERE id=?",
                (left - 1, row["id"]),
            )
            return True

    def queue_gift_effect(
        self, guild_id: int, owner_kind: str, owner_id: int, gift_name: str,
        effect_type: str, value: float, *, effect_owner: str = "user",
        gift_tag: str = "", starts_turn: int = 0, expires_turn: int = 0,
    ) -> None:
        """Deixa o efeito **pendente** para os inícios de rodada seguintes.

        É o mecanismo único de *"por N Rodadas"* e de *"na próxima rodada"*: a
        linha fica aqui e é aplicada em cada `session_round_start` de
        ``turn+1`` até ``turn+N`` — **N** rodadas de verdade, e não uma só. Na
        entrega final a linha é apagada.
        """
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO ego_gift_state
                   (guild_id,owner_kind,owner_id,gift_name,effect_type,value,
                    effect_owner,gift_tag,starts_turn,expires_turn)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(guild_id,owner_kind,owner_id,gift_name,effect_type,
                                window_key,expires_turn)
                   DO UPDATE SET value=value+excluded.value""",
                (guild_id, owner_kind, owner_id, gift_name, effect_type, value,
                 effect_owner, gift_tag, starts_turn + 1,
                 starts_turn + max(1, int(expires_turn or 1))),
            )

    def take_gift_effects(self, guild_id: int, owner_kind: str, owner_id: int, turn: int) -> list[dict]:
        """Efeitos pendentes que valem neste início de rodada.

        Também limpa o que expirou e zera o contador de "1x por rodada": a
        janela é da rodada, então no turno novo o limite recomeça.
        """
        with self.lock, self.connection:
            # Zera o contador de "1x por rodada": a janela é DA rodada, então no
            # turno novo o limite recomeça.
            self.connection.execute(
                """UPDATE ego_gift_state SET activations_left=NULL
                   WHERE guild_id=? AND owner_kind=? AND owner_id=?
                   AND window_key=?""",
                (guild_id, owner_kind, owner_id, f"round:{turn}"),
            )
            # Selecciona ANTES de apagar: é o que faz "por 2 Rodadas" aplicar
            # duas vezes (turnos +1 e +2) e na terceira sair da fila.
            rows = self.connection.execute(
                """SELECT gift_name,effect_type,value,effect_owner,gift_tag,expires_turn
                   FROM ego_gift_state
                   WHERE guild_id=? AND owner_kind=? AND owner_id=? AND effect_type<>''
                   AND starts_turn<=? AND (expires_turn=0 OR expires_turn>=?)""",
                (guild_id, owner_kind, owner_id, turn, turn),
            ).fetchall()
            self.connection.execute(
                """DELETE FROM ego_gift_state
                   WHERE guild_id=? AND owner_kind=? AND owner_id=?
                   AND expires_turn>0 AND expires_turn<=?""",
                (guild_id, owner_kind, owner_id, turn),
            )
        return [dict(r) for r in rows]

    def clear_gift_state(self, guild_id: int, owner_kind: str, owner_id: int) -> None:
        """Limpa pendências e limites da ficha (usado ao iniciar o Encounter)."""
        with self.lock, self.connection:
            self.connection.execute(
                "DELETE FROM ego_gift_state WHERE guild_id=? AND owner_kind=? AND owner_id=?",
                (guild_id, owner_kind, owner_id),
            )

    def active_turn(self, guild_id: int) -> int | None:
        """Turno da batalha ativa do servidor, ou ``None`` se não houver uma.

        O ``on_crit`` chega em ``apply_skill_trigger`` sem rodada, e a Etapa 5
        precisa dela para a janela *"1x por rodada"* e para calcular o
        ``expires_turn`` do *"na próxima rodada"*.
        """
        with self.lock:
            row = self.connection.execute(
                """SELECT turn FROM battle_sessions WHERE guild_id=? AND active=1
                   ORDER BY channel_id DESC LIMIT 1""",
                (guild_id,),
            ).fetchone()
        return int(row["turn"]) if row and row["turn"] else None

    def total_bloodfeast(self, guild_id: int, owner_kind: str, owner_id: int) -> int:
        """Bloodfeast em **Count** da ficha.

        A Falsa Fome da Rosemary É um Unique Bloodfeast (decisão do autor), e as
        skills dela passaram a falar ``bloodfeast`` direto — por isso não existe
        mais "a Falsa Fome mora em ``special_condition``" para somar aqui.

        Antes elas eram coisas separadas: o gift gravava/lia ``bloodfeast`` e a
        Falsa Fome vivia em ``special_condition``, então o gift não via o recurso
        que as skills dela consumiam. A keyword ``unique_bloodfeast`` continua
        existindo (é ela que marca "esta ficha tem Bloodfeast único"), mas não
        participa mais da conta.

        ``special_condition`` sobrou como o "Efeito Trashholder" das outras fichas
        — somar um no Bloodfeast delas seria errado.
        """
        base = self.get_status(guild_id, owner_kind, owner_id, "bloodfeast")
        return base.count if base is not None else 0

    def count_allies_with(self, guild_id: int, owner_kind: str, owner_id: int, keyword: str) -> int:
        """Quantos **sinners do encontro** (o próprio incluído) declaram ``keyword``.

        É o *"3 ou mais aliados da Middle / com Poise"* — 3 no total, porque o
        time do Limbus inclui quem está jogando. Ver ``encounter_member_ids``
        para o que conta como "encontro" hoje.
        """
        wanted = str(keyword).strip().casefold()
        wanted = KEYWORD_ALIASES.get(wanted, wanted)
        members = self.encounter_member_ids(guild_id, owner_kind, owner_id)
        table = "characters" if owner_kind == "player" else "enemies"
        key = "user_id" if owner_kind == "player" else "id"
        marks = ",".join("?" for _ in members)
        with self.lock:
            rows = self.connection.execute(
                f"SELECT keywords FROM {table} WHERE guild_id=? AND {key} IN ({marks})",
                (guild_id, *sorted(members)),
            ).fetchall()
        return sum(1 for row in rows if wanted in normalize_keywords(row["keywords"]))

    def character_uptie(self, guild_id: int, user_id: int) -> int:
        """Uptie 1–5 lido do perfil persistente (o mesmo que a UI já edita)."""
        with self.lock:
            row = self.connection.execute(
                "SELECT profile_json FROM character_profiles WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            ).fetchone()
        if row is None:
            return 1
        try:
            profile = json.loads(row["profile_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return 1
        return max(1, min(5, int(profile.get("uptie", 1) or 1)))

    def ego_gift_limit_warning(self, guild_id: int, owner_kind: str, owner_id: int, gift_count: int) -> str | None:
        """Aviso **não bloqueante** do teto por Uptie (§7.7).

        ``EGO_GIFT_MAX_BY_UPTIE`` vazia → devolve ``None``, ou seja, o
        comportamento de hoje (lista livre) continua intacto.
        """
        if not EGO_GIFT_MAX_BY_UPTIE or owner_kind != "player":
            return None
        uptie = self.character_uptie(guild_id, owner_id)
        limit = EGO_GIFT_MAX_BY_UPTIE.get(uptie)
        if limit is None or gift_count <= limit:
            return None
        return f"Uptie {uptie} comporta {limit} E.G.O Gift e a ficha está com {gift_count}."

    def save_ego_gift(self, guild_id: int, owner_kind: str, owner_id: int, payload: dict) -> dict:
        gift_id = payload.get("id")
        name = str(payload.get("name", "")).strip()
        tier = int(payload.get("tier", 1))
        desc = str(payload.get("description", ""))
        bpm = int(payload.get("base_power_mod", 0))
        cpm = int(payload.get("coin_power_mod", 0))
        clpm = int(payload.get("clash_power_mod", 0))
        olm = int(payload.get("offense_level_mod", 0))
        dlm = int(payload.get("defense_level_mod", 0))
        effects_json = json.dumps(payload.get("effects", []))
        # Bloco 7 — "o gift só vale quando…". Vazio/`self` = sempre vale.
        active_status = str(payload.get("active_status", "") or "").strip().casefold()
        active_tag = str(payload.get("active_tag", "") or "").strip().casefold()
        active_scope = str(payload.get("active_scope", "self") or "self")
        if active_scope not in {"self", "allies"}:
            active_scope = "self"
        active_min = max(0, int(payload.get("active_min", 0) or 0))
        gift_class = str(payload.get("gift_class", "") or "").strip().upper()
        crit_damage_mod = int(payload.get("crit_damage_mod", 0) or 0)
        with self.lock, self.connection:
            if gift_id:
                self.connection.execute(
                    """UPDATE ego_gifts SET name=?, tier=?, description=?, base_power_mod=?, coin_power_mod=?,
                       clash_power_mod=?, offense_level_mod=?, defense_level_mod=?, effects_json=?,
                       active_status=?, active_tag=?, active_scope=?, active_min=?, gift_class=?,
                       crit_damage_mod=?
                       WHERE id=? AND guild_id=? AND owner_kind=? AND owner_id=?""",
                    (name, tier, desc, bpm, cpm, clpm, olm, dlm, effects_json,
                     active_status, active_tag, active_scope, active_min, gift_class,
                     crit_damage_mod, gift_id, guild_id, owner_kind, owner_id),
                )
            else:
                cursor = self.connection.execute(
                    """INSERT INTO ego_gifts (guild_id, owner_kind, owner_id, name, tier, description,
                       base_power_mod, coin_power_mod, clash_power_mod, offense_level_mod, defense_level_mod, effects_json,
                       active_status, active_tag, active_scope, active_min, gift_class, crit_damage_mod)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (guild_id, owner_kind, owner_id, name, tier, desc, bpm, cpm, clpm, olm, dlm, effects_json,
                     active_status, active_tag, active_scope, active_min, gift_class, crit_damage_mod),
                )
                gift_id = cursor.lastrowid
        # Fora do lock: `ego_gift_limit_warning` lê o perfil e adquire o mesmo.
        count = len(self.list_ego_gifts(guild_id, owner_kind, owner_id))
        return {
            "id": gift_id,
            "name": name,
            "limit_warning": self.ego_gift_limit_warning(guild_id, owner_kind, owner_id, count),
        }

    def delete_ego_gift(self, guild_id: int, owner_kind: str, owner_id: int, gift_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "DELETE FROM ego_gifts WHERE id=? AND guild_id=? AND owner_kind=? AND owner_id=?",
                (gift_id, guild_id, owner_kind, owner_id),
            )

    def get_total_ego_gift_modifiers(self, guild_id: int, owner_kind: str, owner_id: int) -> dict:
        with self.lock:
            row = self.connection.execute(
                """SELECT SUM(base_power_mod) as bpm, SUM(coin_power_mod) as cpm,
                          SUM(clash_power_mod) as clpm, SUM(offense_level_mod) as olm,
                          SUM(defense_level_mod) as dlm, SUM(crit_damage_mod) as cdm
                   FROM ego_gifts WHERE guild_id=? AND owner_kind=? AND owner_id=? AND is_active=1""",
                (guild_id, owner_kind, owner_id),
            ).fetchone()
            mods = {
                "base_power_mod": row["bpm"] or 0,
                "coin_power_mod": row["cpm"] or 0,
                "clash_power_mod": row["clpm"] or 0,
                "offense_level_mod": row["olm"] or 0,
                "defense_level_mod": row["dlm"] or 0,
                # Clear Mirror: pontos percentuais somados ao crítico do Poise
                # (que sozinho é Potência × 2%).
                "crit_damage_mod": row["cdm"] or 0,
            }
        # Glimpse of Precognition (EGO_GIFTS.md §1.5): +1 ⬆️ Clash Power para
        # CADA stack. Vira Mods antes do roll, então entra em resolve_clash().
        # Fica fora do `with self.lock` porque get_status adquire o mesmo lock.
        glimpse = self.get_status(guild_id, owner_kind, owner_id, "glimpse_of_precognition")
        if glimpse is not None and glimpse.count > 0:
            mods["clash_power_mod"] += glimpse.count
            # A cada 2 Stack: +1 Coin Power (EGO_GIFTS.md §1.5:67-69).
            # O braço de "moedas negativas → +2 Final Power" ficou DE FORA a
            # pedido do autor: ele não usa moeda negativa e o gift é dele.
            mods["coin_power_mod"] += glimpse.count // 2
        return mods

    def set_battle_participant_ready(
        self, guild_id: int, channel_id: int, user_id: int, ready: bool,
    ) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """UPDATE battle_participants SET ready=?
                   WHERE guild_id=? AND channel_id=? AND user_id=?""",
                (int(ready), guild_id, channel_id, user_id),
            )

    def set_battle_phase(self, guild_id: int, channel_id: int, phase: str):
        if phase not in {"preparation", "declaration", "resolution", "complete"}:
            raise ValueError("Fase de batalha inválida")
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """UPDATE battle_sessions SET phase=?
                   WHERE guild_id=? AND channel_id=? AND active=1""",
                (phase, guild_id, channel_id),
            )
        battle = self.get_battle(guild_id, channel_id) if cursor.rowcount else None
        # `declaration` é onde a rodada realmente começa: é quando os jogadores
        # escolhem as ações. O desenho punha `[Início do Encontro]` em
        # `start_battle()`, mas naquele instante os participantes ainda não
        # entraram no painel (`join_battle` vem depois) — o gift dispararia para
        # uma lista vazia. Aqui já tem gente, então o encontro, o combate e a
        # primeira rodada disparam juntos, nessa ordem.
        if battle is not None and phase == "declaration":
            turn = int(battle["turn"] or 1)
            # Na rodada 1 a ordem é encontro -> combate -> rodada: o gift de
            # "[Primeira Rodada]" precisa ver o que o "[Início do Encontro]"
            # já deixou na ficha.
            if turn <= 1:
                # Encontro novo: pendência e limite da Etapa 5 não atravessam
                # de um Encounter para o outro.
                for linha in self.list_battle_participants(guild_id, channel_id):
                    self.clear_gift_state(guild_id, "player", int(linha["user_id"]))
                self.fire_session(guild_id, channel_id, "session_encounter_start", turn)
                self.fire_session(guild_id, channel_id, "session_combat_start", turn)
            self.fire_session(guild_id, channel_id, "session_round_start", turn)
        return battle

    def current_turn(self, guild_id: int, channel_id: int) -> int:
        """Turno da batalha ativa (1 quando não há batalha)."""
        with self.lock:
            row = self.connection.execute(
                """SELECT turn FROM battle_sessions
                   WHERE guild_id=? AND channel_id=? AND active=1""",
                (guild_id, channel_id),
            ).fetchone()
        return int(row["turn"]) if row and row["turn"] else 1

    def fire_session(self, guild_id: int, channel_id: int, trigger: str, turn: int) -> None:
        """Chama o gancho de sessão, se o bot ligou um. Nunca levanta erro.

        Um gift mal escrito não pode derrubar a virada de rodada do grupo — o
        mesmo espírito de `_effects_from_row`, que devolve tupla vazia em vez de
        estourar no meio do combate.
        """
        hook = self.session_hook
        if hook is None:
            return
        try:
            hook(guild_id, channel_id, trigger, turn)
        except Exception:  # noqa: BLE001 - gancho opcional nunca quebra o fluxo
            import traceback
            traceback.print_exc()

    def reset_battle_readiness(self, guild_id: int, channel_id: int) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE battle_participants SET ready=0 WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )
