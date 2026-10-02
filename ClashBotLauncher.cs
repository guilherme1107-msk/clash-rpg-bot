using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

public static class ClashBotLauncher
{
    static readonly string Root = AppDomain.CurrentDomain.BaseDirectory;
    static Label status;

    [STAThread]
    public static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var form = new Form {
            Text = "ClashBot - Central de Inicialização", StartPosition = FormStartPosition.CenterScreen,
            ClientSize = new Size(920, 660), BackColor = Color.FromArgb(16, 13, 15),
            ForeColor = Color.FromArgb(238, 228, 220), Font = new Font("Segoe UI", 11),
            FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false
        };
        using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("ClashBotBackdrop"))
            if (stream != null) { using (var image = Image.FromStream(stream)) form.BackgroundImage = new Bitmap(image); form.BackgroundImageLayout = ImageLayout.Stretch; }

        var frame = new Panel { Left = 18, Top = 16, Width = 884, Height = 628, BackColor = Color.FromArgb(220, 12, 10, 12) };
        form.Controls.Add(frame);
        var title = new Label { Text = "⌁  CLASHBOT", Left = 30, Top = 26, Width = 760, Height = 52,
            Font = new Font("Georgia", 30, FontStyle.Bold), ForeColor = Color.FromArgb(236, 80, 94), BackColor = Color.Transparent };
        var subtitle = new Label { Text = "CENTRAL DE INICIALIZAÇÃO  //  SISTEMAS VINCULADOS", Left = 34, Top = 84, Width = 760, Height = 25, ForeColor = Color.FromArgb(205, 175, 136), BackColor = Color.Transparent, Font = new Font("Consolas", 10, FontStyle.Bold) };
        frame.Controls.Add(title); frame.Controls.Add(subtitle);

        var all = MakeButton("▶  LIGAR TUDO", "Inicia somente a Activity e o bot.", 24, 126, Color.FromArgb(156, 42, 57), (s,e) => { Start("start_discord_activity.bat"); Start("start_control_center.bat"); SetStatus("Activity e bot foram abertos sem túnel público."); });
        all.Width = 836; all.Height = 88;
        frame.Controls.Add(all);
        frame.Controls.Add(MakeButton("◉  ACTIVITY", "Abre o servidor do painel dentro do Discord.", 24, 238, Color.FromArgb(65, 36, 43), (s,e) => { Start("start_discord_activity.bat"); SetStatus("[ACTIVITY] Servidor iniciado."); }));
        frame.Controls.Add(MakeButton("✦  CENTRAL DO BOT", "Abre o painel de controle e liga o bot.", 460, 238, Color.FromArgb(39, 31, 35), (s,e) => { Start("start_control_center.bat"); SetStatus("[BOT] Central aberta."); }));
        frame.Controls.Add(MakeButton("■  DESLIGAR TUDO", "Encerra o bot, a Activity e a Central.", 24, 382, Color.FromArgb(63, 27, 32), (s,e) => { Start("stop_all.bat"); SetStatus("[SISTEMA] Encerramento solicitado com segurança."); }));
        status = new Label { Text = "◆  PRONTO — escolha “LIGAR TUDO” para o uso normal.", Left = 28, Top = 554, Width = 800, Height = 34, ForeColor = Color.FromArgb(228, 190, 121), BackColor = Color.Transparent, Font = new Font("Consolas", 10) };
        frame.Controls.Add(status);
        Application.Run(form);
    }

    static Button MakeButton(string text, string hint, int left, int top, Color color, EventHandler click)
    {
        var button = new Button { Text = text + "\r\n" + hint, Left = left, Top = top, Width = 400, Height = 108,
            FlatStyle = FlatStyle.Flat, BackColor = color, ForeColor = Color.White, TextAlign = ContentAlignment.MiddleLeft,
            Font = new Font("Segoe UI", 13, FontStyle.Bold), Cursor = Cursors.Hand };
        button.FlatAppearance.BorderColor = Color.FromArgb(164, 85, 92);
        button.FlatAppearance.BorderSize = 1; button.Click += click;
        return button;
    }

    static void Start(string file)
    {
        string path = Path.Combine(Root, file);
        if (!File.Exists(path)) { SetStatus("Arquivo não encontrado: " + file); return; }
        Process.Start(new ProcessStartInfo { FileName = "cmd.exe", Arguments = "/c start \"ClashBot\" \"" + path + "\"", WorkingDirectory = Root, UseShellExecute = true });
    }

    static void SetStatus(string message) { status.Text = message; }
}
