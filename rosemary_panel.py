"""Projeção somente-leitura do estado do ClashBot para o painel da Rosemary."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from database import Database

COMBAT_PASSIVES = (
    ("possua-me", "Possua-me, Ó Besta de Sangue", "A devoção cresce com a Falsa Fome consumida."),
    ("ajoelhe-se", "Ajoelhe-se, Ó Besta Indigna", "A corrente responde quando os Selos cedem."),
    ("delirio", "Delírio de Pertencimento", "Estado manifestado em +45 SP."),
    ("correntes", "As Correntes Não São Minhas", "A libertação altera o kit definido pelo ClashBot."),
)
RP_PASSIVES = (
    ("falsa-fome-rp", "Falsa Fome", "Reconhece rastros e sinais ligados a sangue."),
    ("adora-rp", "Conheça Aquilo que Adora", "Conhecimento dedicado sobre Bloodfiends."),
    ("predadora-rp", "Predadora Ensaiada", "Presença predatória aprendida e deliberada."),
    ("anatomia-rp", "Anatomia Predatória", "Medicina aplicada a cortes, mordidas e perda de sangue."),
)
CONTENT_PATH = Path(__file__).with_name("rosemary_content.json")


def load_rosemary_content():
    try:
        return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"skills": [], "roleplay_passives": []}


def save_rosemary_content(payload, database_file=None):
    content = load_rosemary_content()
    full_sheet = payload.get("sheet")
    if full_sheet is not None:
        if not isinstance(full_sheet, dict):
            raise ValueError("Ficha inválida.")
        allowed = {"profile", "uptie", "uptie_levels", "level_rules", "level_milestones", "combat_passives", "combat_statuses", "skills", "roleplay_passives", "proficiencies", "narrative"}
        candidate = {key: value for key, value in full_sheet.items() if key in allowed}
        if len(json.dumps(candidate, ensure_ascii=False)) > 100_000:
            raise ValueError("A ficha excede o tamanho permitido.")
        content.update(candidate)
        CONTENT_PATH.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        if database_file and payload.get("guild_id") and payload.get("owner_id"):
            sync_rosemary_sheet(database_file, content, int(payload["guild_id"]), int(payload["owner_id"]))
        return {"ok": True, "content": content}
    incoming = payload.get("roleplay_passives", [])
    if not isinstance(incoming, list):
        raise ValueError("Passivas de RP inválidas.")
    cleaned = []
    for item in incoming[:20]:
        name, description = str(item.get("name", "")).strip()[:80], str(item.get("description", "")).strip()[:2000]
        if name:
            cleaned.append({"id": str(item.get("id", name.casefold().replace(" ", "-")))[:80], "name": name, "description": description})
    content["roleplay_passives"] = cleaned
    CONTENT_PATH.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "content": content}


def _rosemary_skill_rows(uptie: int, unpacked: bool):
    """Usa os modelos do motor do ClashBot; o painel nunca é fonte de cálculo."""
    from bot import SkillEffect, skill_template

    sealed = [("please_a_little", "s1", "attack"), ("i_can_be_useful", "s2", "attack")]
    unsealed = [("do_not_deny", "s1", "attack"), ("kneel", "s2", "attack")]
    if uptie >= 3:
        sealed.append(("accept_my_offering", "s3", "attack"))
    if unpacked:
        unsealed.append(("you_do_not_deserve_blood", "s3", "attack"))
    selected = unsealed if unpacked else sealed
    result = []
    for template, slot, level_type in selected:
        skill = skill_template(template)
        result.append((skill.name, skill.base_power, skill.coin_power, skill.coins, skill.description, level_type, slot, [vars(effect) for effect in skill.effects]))
    defense = (
        "Por Favor... Não me Machuque Muito.", 4, 10, 1,
        "[3 / 2 / 1 Selos] • Gloom • Esquiva • Attack Weight 1\n“Desculpe... eu ainda preciso ficar inteira.”",
        "evade", "d1",
        [
            # A Falsa Fome É Bloodfeast (decisão do autor): as skills dela speak
            # `bloodfeast`, e o E.G.O Gift enxerga o mesmo recurso. O painel
            # continua chamando de Falsa Fome na tela.
            vars(SkillEffect("on_use", "bloodfeast", 0, count=10)),
            vars(SkillEffect("on_evade", "bloodfeast", 0, count=5)),
            vars(SkillEffect("after_attack", "consume_bloodfeast", 20)),
            vars(SkillEffect("after_attack", "consume_devotion_repressed", 1)),
        ],
    )
    return [*result, defense]


def sync_rosemary_sheet(database_file, content, guild_id: int, owner_id: int):
    """Espelha alterações permitidas do painel na ficha real já vinculada."""
    profile = content.get("profile", {})
    attributes = profile.get("attributes", {})
    uptime = max(1, min(5, int(content.get("uptie", 1))))
    with sqlite3.connect(database_file) as db:
        db.row_factory = sqlite3.Row
        if db.execute("SELECT 1 FROM characters WHERE guild_id=? AND user_id=?", (guild_id, owner_id)).fetchone() is None:
            raise ValueError("Ficha vinculada não encontrada no ClashBot.")
        sp = max(-45, min(45, int(profile.get("sanity", 0))))
        offense = int(profile.get("offense_level", 0))
        defense = int(profile.get("defense_level", 0))
        tags = json.dumps(["rosemary", "bloodfiend", f"uptie-{uptime}"], ensure_ascii=False)
        db.execute(
            "UPDATE characters SET sp=?, offense_level=?, defense_level=?, tags_json=? WHERE guild_id=? AND user_id=?",
            (sp, offense, defense, tags, guild_id, owner_id),
        )
        normalized_profile = {
            "version": 1, "uptie": uptime, "level": int(profile.get("level", 1)),
            "hp": int(profile.get("hp", 1)), "max_hp": int(profile.get("max_hp", profile.get("hp", 1))),
            "sp": sp, "light": int(profile.get("light", 0)), "max_light": int(profile.get("max_light", 0)),
            "stagger": int(profile.get("stagger", 0)), "max_stagger": int(profile.get("max_stagger", 0)),
            "rd": int(profile.get("damage_reduction", 0)), "movement": profile.get("movement", "9 m"),
            "offense_level": offense, "defense_level": defense,
            "attributes": {"strength": attributes.get("Força", 10), "dexterity": attributes.get("Destreza", 10), "constitution": attributes.get("Constituição", 10), "intelligence": attributes.get("Inteligência", 10), "wisdom": attributes.get("Sabedoria", 10), "charisma": attributes.get("Carisma", 10)},
            "resistances": [{"name": key, "value": value} for key, value in profile.get("resistances", {}).items()],
            "records": content.get("narrative", {}),
        }
        db.execute(
            "INSERT INTO character_profiles(guild_id,user_id,profile_json) VALUES(?,?,?) ON CONFLICT(guild_id,user_id) DO UPDATE SET profile_json=excluded.profile_json,updated_at=CURRENT_TIMESTAMP",
            (guild_id, owner_id, json.dumps(normalized_profile, ensure_ascii=False)),
        )
        state = db.execute("SELECT unpacked FROM rosemary_states WHERE guild_id=? AND user_id=?", (guild_id, owner_id)).fetchone()
        unpacked = bool(state["unpacked"]) if state else False
        db.execute("DELETE FROM passives WHERE guild_id=? AND owner_kind='player' AND owner_id=?", (guild_id, owner_id))
        combat_p = content.get("combat_passives", [])
        rp_p = content.get("roleplay_passives", [])
        for p in combat_p + rp_p:
            p_name = p.get("name", "")
            p_desc = p.get("description", "")
            if p_name:
                db.execute(
                    "INSERT INTO passives(guild_id, owner_kind, owner_id, name, description, effects_json) VALUES(?, 'player', ?, ?, ?, '[]')",
                    (guild_id, owner_id, p_name, p_desc),
                )
        
        # Sync Rosemary's Tier V E.G.O Gifts if not present
        existing_gifts = db.execute("SELECT name FROM ego_gifts WHERE guild_id=? AND owner_kind='player' AND owner_id=?", (guild_id, owner_id)).fetchall()
        existing_names = {r["name"] for r in existing_gifts}
        rosemary_gifts = [
            {
                "name": "Imperfect Eye of Precognition", "tier": 5,
                "description": "Uma prótese de alguém\n[Efeito se aplica ao usuário]\n- Em Clash, ganhe 1 <:GlimpseofPrecognition:1553633485090988052> Glimpse of Precognition em todo Clash Win. Infrinja 2 Tremor e Burn no alvo (10 vezes por habilidade).\n- [Clash Win] Ative Amplitude Conversion em Tremor - Scorch e ative Tremor Burst no alvo principal. Alvo perde 1 Tremor Count.\n- [Ao Critar] Ative Tremor Burst. Alvo perde 1 Tremor Count (2 vezes por rodada).\n\n<:GlimpseofPrecognition:1553633485090988052> Glimpse of Precognition\n- Max Stack: 5\n- +1 Clash Power para cada Stack\n- Cada 2 Stack:\n  • Habilidades de moedas positivas, ganham +1 Coin Power\n  • Habilidades de moedas negativas, ganham +2 Final Power\n- Expira na próxima rodada depois de chegar em 5 Stack",
                "bpm": 0, "cpm": 0, "clpm": 0, "olm": 0, "dlm": 0
            },
            {
                "name": "Carousel Figurine", "tier": 5,
                "description": "Um pequeno carrossel que parece ser daquele local\n[Primeira Rodada] Aumente Bloodfeast em 300\nDobre a quantidade de Bloodfeast ganho por Bleed\nAo usar uma habilidade que consome Bloodfeast, no final do ataque, consuma adicionalmente Bloodfeast igual a quantidade que a habilidade consumiu\n\n[Exclusivo para personagens de La Manchaland]\nQuando um personagem de La Manchaland entra em combate, o personagem ganha seu respectivo efeito: ???",
                "bpm": 0, "cpm": 0, "clpm": 0, "olm": 0, "dlm": 0
            },
            {
                "name": "The Family's Resentment", "tier": 5,
                "description": "Foi um ultimo show realmente naquele local\nDobre toda quantidade de Bloodfeast gerado no combate\nHabilidades que infringem Bleed Potency, Bleed Count, ou Unique Bleed: Curam 30% do HP como dano causado no final da habilidade (max 20)\n• Se um personagem curou usando o efeito acima, ele ganha 1 Final Power no inicio da proxima rodada (max 3)\n\nPara cada 50 Bloodfeast Consumido (Compartilhado), todos os aliados ganham 1 Offense Level no inicio da proxima rodada (max 6)\nPara cada personagem de La Manchaland também ganha 2 Offense Level para cada 30 Bloodfeast Consumido por cada personagem (max 6)",
                "bpm": 0, "cpm": 0, "clpm": 0, "olm": 0, "dlm": 0
            }
        ]
        for g in rosemary_gifts:
            if g["name"] not in existing_names:
                db.execute(
                    """INSERT INTO ego_gifts(guild_id, owner_kind, owner_id, name, tier, description,
                       base_power_mod, coin_power_mod, clash_power_mod, offense_level_mod, defense_level_mod, effects_json)
                       VALUES(?, 'player', ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]')""",
                    (guild_id, owner_id, g["name"], g["tier"], g["description"], g["bpm"], g["cpm"], g["clpm"], g["olm"], g["dlm"]),
                )
        db.execute("INSERT INTO rosemary_events(guild_id,user_id,kind,message) VALUES(?,?,?,?)", (guild_id, owner_id, "sheet", f"Ficha sincronizada pelo painel • Uptie {uptime}"))


def update_rosemary_mechanics(database_file, payload):
    guild_id, owner_id = int(payload["guild_id"]), int(payload["owner_id"])
    with sqlite3.connect(database_file) as db:
        db.row_factory = sqlite3.Row
        character = db.execute("SELECT 1 FROM characters WHERE guild_id=? AND user_id=?", (guild_id, owner_id)).fetchone()
        if character is None:
            raise ValueError("Ficha vinculada não encontrada.")
        db.execute("INSERT OR IGNORE INTO rosemary_states(guild_id,user_id) VALUES(?,?)", (guild_id, owner_id))
        state = db.execute("SELECT * FROM rosemary_states WHERE guild_id=? AND user_id=?", (guild_id, owner_id)).fetchone()
        seals = max(0, min(3, int(payload.get("seals", state["seals"]))))
        maximum = max(1, min(999, int(payload.get("false_hunger_max", state["false_hunger_max"]))))
        hunger = max(0, min(maximum, int(payload.get("false_hunger", 0))))
        devotion_max = {3: 1, 2: 2, 1: 2, 0: 0}[seals]
        devotion = max(0, min(devotion_max, int(payload.get("devotion", 0))))
        db.execute("UPDATE rosemary_states SET seals=?,unpacked=?,false_hunger_max=?,devotion_max=? WHERE guild_id=? AND user_id=?", (seals, int(seals == 0), maximum, devotion_max, guild_id, owner_id))
        for status_type, count in (("bloodfeast", hunger), ("devotion_repressed", devotion)):
            db.execute("INSERT INTO combat_statuses(guild_id,owner_kind,owner_id,status_type,potency,count) VALUES(?,'player',?,?,1,?) ON CONFLICT(guild_id,owner_kind,owner_id,status_type) DO UPDATE SET potency=1,count=excluded.count", (guild_id, owner_id, status_type, count))
        db.execute("INSERT INTO rosemary_events(guild_id,user_id,kind,message) VALUES(?,?,?,?)", (guild_id, owner_id, "manual", "Correção manual aplicada pelo painel"))
    return {"ok": True}


def _meter(current: int, maximum: int) -> dict:
    maximum = max(1, int(maximum))
    return {"current": max(0, min(int(current), maximum)), "maximum": maximum}


class RosemaryPanelRepository:
    """Traduz tabelas existentes; nunca escreve nem resolve regras de combate."""
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _resolve_character(self, db, guild_id, owner_id):
        clauses, params = [], []
        if guild_id is not None:
            clauses.append("guild_id=?"); params.append(guild_id)
        if owner_id is not None:
            clauses.append("user_id=?"); params.append(owner_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        if owner_id is not None:
            return db.execute(f"SELECT * FROM characters {where} ORDER BY guild_id LIMIT 1", params).fetchone()
        joiner = " AND " if where else "WHERE "
        named = db.execute(f"SELECT * FROM characters {where}{joiner}lower(name) LIKE '%rosemary%' LIMIT 1", params).fetchone()
        return named

    @staticmethod
    def _status(db, guild_id, owner_id, kind):
        row = db.execute("SELECT potency,count FROM combat_statuses WHERE guild_id=? AND owner_kind='player' AND owner_id=? AND status_type=?", (guild_id, owner_id, kind)).fetchone()
        return {"potency": int(row["potency"]), "count": int(row["count"])} if row else {"potency": 0, "count": 0}

    @staticmethod
    def _skills(db, guild_id, owner_id, unpacked):
        rows = db.execute("SELECT id,name,base_power,coin_power,coins,unbreakable_coins,description,level_type,effects_json,coin_layout_json,skill_slot FROM skills WHERE guild_id=? AND owner_id=? ORDER BY id", (guild_id, owner_id)).fetchall()
        result = []
        for i, row in enumerate(rows):
            try: effects = json.loads(row["effects_json"] or "[]")
            except (TypeError, json.JSONDecodeError): effects = []
            low, high = sorted((int(row["base_power"]), int(row["base_power"]) + int(row["coin_power"]) * int(row["coins"])))
            saved_slot = str(row["skill_slot"] or "").casefold()
            slot = {"s1": "S1", "s2": "S2", "s3": "S3", "d1": "DEF", "def": "DEF"}.get(saved_slot, f"S{i+1}")
            result.append({"id": str(row["id"]), "name": row["name"], "slot": slot, "version": "unsealed" if unpacked else "sealed", "description": row["description"] or "Efeitos resolvidos pelo ClashBot.", "cost": None, "base_power": int(row["base_power"]), "coin_power": int(row["coin_power"]), "coins": int(row["coins"]), "unbreakable_coins": int(row["unbreakable_coins"]), "skill_type": row["level_type"], "range": {"minimum": low, "maximum": high}, "effects": effects})
        return result

    @staticmethod
    def _icons():
        hunger_id = "1538020913419780096"
        devotion_id = "1538031688624382063"
        seal_id = "1538020969803944046"
        return {"false_hunger": {"kind": "discord", "text": "", "url": f"https://cdn.discordapp.com/emojis/{hunger_id}.webp?size=128&quality=lossless"}, "devotion": {"kind": "discord", "text": "", "url": f"https://cdn.discordapp.com/emojis/{devotion_id}.webp?size=128&quality=lossless"}, "seal": {"kind": "discord", "text": "", "url": f"https://cdn.discordapp.com/emojis/{seal_id}.webp?size=128&quality=lossless"}}

    @staticmethod
    def _passives(sp, unpacked, uptie=1):
        active_id = "correntes" if int(uptie) >= 4 else "delirio" if sp >= 45 else "possua-me"
        content = load_rosemary_content()
        configured = content.get("combat_passives") or [{"id": key, "name": name, "description": desc} for key, name, desc in COMBAT_PASSIVES]
        items = [{**item, "active": item["id"] == active_id, "category": "sanity" if item["id"] == "delirio" else "combat"} for item in configured]
        draft = content.get("roleplay_passives", [])
        items += [{"id": item["id"], "name": item["name"], "description": item.get("description", ""), "active": False, "category": "roleplay"} for item in draft]
        return items, next(item for item in items if item["active"])

    @staticmethod
    def _logs(db, guild_id, owner_id, limit):
        rows = db.execute("SELECT id,created_at,player_skill,target_enemy,action_type,final_damage FROM battle_player_actions WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT ?", (guild_id, owner_id, limit)).fetchall()
        return [{"id": str(row["id"]), "timestamp": row["created_at"], "kind": "combat", "message": f"{row['player_skill']} → {row['target_enemy']} ({row['action_type']})", "amount": int(row["final_damage"])} for row in rows]

    def snapshot(self, guild_id=None, owner_id=None, limit=12):
        if not self.path.is_file():
            return self.fallback("Banco do ClashBot ainda não foi criado.")
        with closing(self._connect()) as db:
            character = self._resolve_character(db, guild_id, owner_id)
            if character is None:
                return self.fallback("Rosemary ainda não possui ficha neste banco.")
            gid, uid, sp = int(character["guild_id"]), int(character["user_id"]), int(character["sp"])
            profile = load_rosemary_content().get("profile", {})
            stored_profile = db.execute(
                "SELECT profile_json FROM character_profiles WHERE guild_id=? AND user_id=?",
                (gid, uid),
            ).fetchone()
            if stored_profile:
                try:
                    profile = {**profile, **json.loads(stored_profile["profile_json"] or "{}")}
                except (TypeError, json.JSONDecodeError):
                    pass
            active_encounter = db.execute(
                """SELECT 1 FROM battle_participants p JOIN battle_sessions b
                   ON b.guild_id=p.guild_id AND b.channel_id=p.channel_id
                   WHERE p.guild_id=? AND p.user_id=? AND b.active=1 LIMIT 1""",
                (gid, uid),
            ).fetchone()
            if active_encounter:
                mechanics = Database(str(self.path))
                mechanics.setup()
                try:
                    mechanics.check_rosemary_hp_trigger(
                        gid, uid, int(profile.get("hp", 0)), int(profile.get("max_hp", 0)),
                    )
                finally:
                    mechanics.close()
            hunger = self._status(db, gid, uid, "bloodfeast")
            devotion = self._status(db, gid, uid, "devotion_repressed")
            rosemary = db.execute("SELECT * FROM rosemary_states WHERE guild_id=? AND user_id=?", (gid, uid)).fetchone()
            seals = max(0, min(3, int(rosemary["seals"]))) if rosemary else 3
            unpacked = bool(rosemary["unpacked"]) if rosemary else seals == 0
            passives, active = self._passives(sp, unpacked, profile.get("uptie", 1))
            state = {
                "character_id": str(uid), "guild_id": str(gid), "name": "Rosemary Véspera", "sheet_name": character["name"], "title": "A Falsa Bloodfiend",
                "hp": _meter(profile.get("hp", 91), profile.get("max_hp", profile.get("hp", 91))), "sp": {"current": sp, "maximum": 45}, "light": _meter(profile.get("light", os.getenv("ROSEMARY_LIGHT", 3)), profile.get("max_light", os.getenv("ROSEMARY_MAX_LIGHT", 3))),
                "false_hunger": _meter(hunger["count"], rosemary["false_hunger_max"] if rosemary else os.getenv("ROSEMARY_FALSE_HUNGER_MAX", 100)), # O contador real é `characters.bloodfeast_consumed` — é o que o consumo
# escreve. `rosemary_states.false_hunger_consumed_total` ficou para trás
# (ninguém chama `record_rosemary_consumption` anymore), então serve só de
# piso para fichas antigas que ainda não rodaram um consumo.
"false_hunger_consumed": max(int(character["bloodfeast_consumed"]), int(rosemary["false_hunger_consumed_total"]) if rosemary else 0),
                "seals": seals, "devotion": {"current": devotion["count"], "maximum": int(rosemary["devotion_max"]) if rosemary else {3: 1, 2: 2, 1: 2, 0: 0}[seals]}, "haste": {"active": int(rosemary["haste_active"]) if rosemary else 0, "pending": int(rosemary["haste_pending"]) if rosemary else 0}, "hp_trigger_used": bool(rosemary["hp_trigger_used"]) if rosemary else False, "sanity_state": "positive" if sp >= 45 else "negative" if sp <= -45 else "normal",
                "stance": "unpacked" if unpacked else "fractured" if seals < 3 else "sealed", "unpacked": unpacked, "active_passive": active, "skills": self._skills(db, gid, uid, unpacked) or self._draft_skills(unpacked), "passives": passives,
                "quote": "Possua-me, ó Besta de Sangue.", "profile": load_rosemary_content().get("profile", {}), "sheet_content": load_rosemary_content(), "combat_statuses": load_rosemary_content().get("combat_statuses", []), "icons": self._icons(), "updated_at": datetime.fromtimestamp(self.path.stat().st_mtime, timezone.utc).isoformat(), "source": "bot",
                "field_sources": {"sp": "characters.sp", "skills": "skills + rosemary_states.unpacked", "false_hunger": "combat_statuses.bloodfeast", "false_hunger_consumed": "characters.bloodfeast_consumed (+ rosemary_states legado)", "devotion": "combat_statuses.devotion_repressed", "hp": "rosemary_content.profile", "light": "config", "seals": "rosemary_states.seals"},
            }
            rosemary_logs = db.execute("SELECT id,created_at,kind,message,amount FROM rosemary_events WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT ?", (gid, uid, limit)).fetchall() if rosemary else []
            custom_log = [{"id": f"rosemary-{row['id']}", "timestamp": row["created_at"], "kind": row["kind"], "message": row["message"], "amount": row["amount"]} for row in rosemary_logs]
            return {"state": state, "log": (custom_log + self._logs(db, gid, uid, limit))[:limit], "fallback_reason": None}

    @staticmethod
    def fallback(reason):
        profile = load_rosemary_content().get("profile", {})
        passives, active = RosemaryPanelRepository._passives(profile.get("sanity", 45), False, profile.get("uptie", 1))
        state = {"character_id": "rosemary-vespera", "guild_id": None, "name": "Rosemary Véspera", "sheet_name": None, "title": "A Falsa Bloodfiend", "hp": _meter(profile.get("hp", 104), profile.get("max_hp", 104)), "sp": {"current": profile.get("sanity", 45), "maximum": 45}, "light": _meter(profile.get("light", 3), profile.get("max_light", 3)), "false_hunger": _meter(0, 100), "false_hunger_consumed": 0, "seals": 3, "devotion": _meter(1, 1), "haste": {"active": 0, "pending": 0}, "hp_trigger_used": False, "sanity_state": "positive", "stance": "sealed", "unpacked": False, "active_passive": active, "skills": RosemaryPanelRepository._draft_skills(False), "passives": passives, "quote": "Possua-me, ó Besta de Sangue.", "profile": profile, "sheet_content": load_rosemary_content(), "combat_statuses": load_rosemary_content().get("combat_statuses", []), "icons": RosemaryPanelRepository._icons(), "updated_at": datetime.now(timezone.utc).isoformat(), "source": "mock", "field_sources": {}}
        return {"state": state, "log": [{"id": "fallback", "timestamp": "agora", "kind": "system", "message": reason, "amount": None}], "fallback_reason": reason}

    @staticmethod
    def _draft_skills(unpacked):
        skills = load_rosemary_content().get("skills", [])
        selected = [item for item in skills if (item.get("version") == "unsealed") == unpacked]
        result = []
        for item in selected:
            skill = dict(item); low, high = sorted((skill["base_power"], skill["base_power"] + skill["coin_power"] * skill["coins"]))
            skill.update({"range": {"minimum": low, "maximum": high}, "effects": [], "unbreakable_coins": 0, "skill_type": "attack", "cost": None})
            result.append(skill)
        return result
