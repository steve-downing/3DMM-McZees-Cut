// McZee's Cut: a small Windows app around render-folder.ps1, for people who
// would rather not use the command line. Pick movies, pick a style, pick
// what to make, press the button.
//
// Built with the C# compiler that ships with Windows (.NET Framework 4.x), so
// it sticks to C# 5. It lives next to render-folder.ps1 in the package.
//
// Command line (all optional; used by CI, and by anything that wants to hand
// it movies):
//   McZeesCut.exe [movie.3mm | folder]... [--out <folder>] [--style improved|faithful]
//                 [--make mp4,crt,sbs,anaglyph,avi,sounds] [--go] [--close-when-done]
//                 [--screenshot <file.png>]
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

static class Program
{
    [DllImport("user32.dll")]
    static extern bool SetProcessDPIAware();

    [STAThread]
    static int Main(string[] args)
    {
        try { SetProcessDPIAware(); } catch { }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var form = new MainForm(args);
        Application.Run(form);
        return form.ExitCode;
    }
}

class Choice
{
    public string Key, Format, Label, Hint;
    public bool Default;
    public CheckBox Box;
    public Choice(string key, string format, string label, string hint, bool def)
    {
        Key = key; Format = format; Label = label; Hint = hint; Default = def;
    }
}

class MainForm : Form
{
    public int ExitCode = 0;

    readonly string appDir = AppDomain.CurrentDomain.BaseDirectory;
    readonly ListBox movieList = new ListBox();
    readonly RadioButton improved = new RadioButton();
    readonly RadioButton faithful = new RadioButton();
    readonly TextBox outBox = new TextBox();
    readonly Button goButton = new Button();
    readonly Button cancelButton = new Button();
    readonly Button openButton = new Button();
    readonly ProgressBar progress = new ProgressBar();
    readonly Label status = new Label();
    readonly CheckBox detailsBox = new CheckBox();
    readonly TextBox log = new TextBox();
    readonly ToolTip tips = new ToolTip();
    readonly List<Choice> choices = new List<Choice>
    {
        new Choice("mp4", "2d", "Video (MP4)",
            "The movie as a regular video file that plays on anything.", true),
        new Choice("crt", "crt", "90s monitor look (4K MP4)",
            "The movie as it looked on a mid-90s computer screen: scanlines, glowing phosphors. A large 4K file.", false),
        new Choice("sbs", "sbs", "3D for VR and 3D TVs (MP4)",
            "Real 3D: a picture for each eye, side by side. Play it in 3D or side-by-side mode.", false),
        new Choice("anaglyph", "anaglyph", "3D for red/cyan glasses (MP4)",
            "3D you can watch on any screen with red/cyan paper glasses.", false),
        new Choice("avi", "avi", "Windows 95/98 video (AVI)",
            "A small video that plays on an old Windows 95 or 98 PC with nothing extra installed.", false),
        new Choice("sounds", null, "The movie's sounds (ZIP)",
            "The voices, sound effects and music added to the movie, as audio files.", false),
    };

    Process proc;
    string stageDir;
    string outDir;
    bool cancelled;
    bool autoGo, closeWhenDone;
    string screenshot;
    bool needsSetup;

    public MainForm(string[] args)
    {
        Text = "McZee's Cut";
        AutoScaleDimensions = new SizeF(96f, 96f);   // laid out at 100%; scaled up on high-DPI screens
        AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 9f);
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(560, 480);
        Size = new Size(660, 660);
        AllowDrop = true;
        BuildLayout();
        outBox.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyVideos), "McZee's Cut");
        ParseArgs(args);
        UpdateButtons();
        DragEnter += OnDragEnter;
        DragDrop += OnDragDrop;
        FormClosing += OnClosing;
        Shown += delegate
        {
            if (screenshot != null) SaveScreenshot(screenshot);
            if (autoGo) Go();
        };
    }

    // ---- layout ---------------------------------------------------------
    void BuildLayout()
    {
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, Padding = new Padding(12), AutoScroll = true };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        Controls.Add(root);

        // movies
        var movies = Section("1. Movies");
        movieList.SelectionMode = SelectionMode.MultiExtended;
        movieList.IntegralHeight = false;
        movieList.Height = 84;
        movieList.Anchor = AnchorStyles.Left | AnchorStyles.Right;
        movieList.AllowDrop = true;
        movieList.DragEnter += OnDragEnter;
        movieList.DragDrop += OnDragDrop;
        movieList.SelectedIndexChanged += delegate { UpdateButtons(); };
        movieList.KeyDown += (s, e) => { if (e.KeyCode == Keys.Delete) RemoveSelected(); };
        var movieButtons = Row();
        movieButtons.Controls.Add(MakeButton("Add movies...", delegate { AddMoviesDialog(); }));
        movieButtons.Controls.Add(MakeButton("Add a folder...", delegate { AddFolderDialog(); }));
        movieButtons.Controls.Add(MakeButton("Remove", delegate { RemoveSelected(); }));
        movieButtons.Controls.Add(new Label { Text = "or drag .3mm files here", AutoSize = true, ForeColor = SystemColors.GrayText,
            Margin = new Padding(6, 8, 0, 0) });
        Add(movies, movieList);
        Add(movies, movieButtons);

        // style
        var style = Section("2. Style");
        improved.Text = "Improved: smooth motion, and the music dips while characters talk (recommended)";
        faithful.Text = "Faithful: exactly as 3D Movie Maker played it";
        foreach (var r in new[] { improved, faithful }) { r.AutoSize = true; r.Margin = new Padding(3, 2, 3, 2); Add(style, r); }
        improved.Checked = true;
        tips.SetToolTip(improved, "3D Movie Maker animates at 6 frames a second. This adds in-between frames for smooth 24 fps motion,\n" +
            "and turns the music down a little whenever someone is speaking.");
        tips.SetToolTip(faithful, "The movie's original 6 frames a second, and its original music levels.");

        // what to make
        var make = Section("3. Make");
        var grid = new TableLayoutPanel { ColumnCount = 2, AutoSize = true, Anchor = AnchorStyles.Left | AnchorStyles.Right, Margin = new Padding(0) };
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        int half = (choices.Count + 1) / 2;
        for (int k = 0; k < choices.Count; k++)
        {
            var c = choices[k];
            c.Box = new CheckBox { Text = c.Label, AutoSize = true, Checked = c.Default, Margin = new Padding(3, 2, 3, 2) };
            c.Box.CheckedChanged += delegate { UpdateButtons(); };
            tips.SetToolTip(c.Box, c.Hint);
            grid.Controls.Add(c.Box, k / half, k % half);
        }
        Add(make, grid);
        Add(make, new Label { Text = "Hover over a choice to see what it is.", AutoSize = true, ForeColor = SystemColors.GrayText,
            Margin = new Padding(3, 4, 3, 0) });

        // where
        var where = Section("4. Save to");
        var whereRow = new TableLayoutPanel { ColumnCount = 2, AutoSize = true, Anchor = AnchorStyles.Left | AnchorStyles.Right, Margin = new Padding(0) };
        whereRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        whereRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        outBox.Anchor = AnchorStyles.Left | AnchorStyles.Right;
        whereRow.Controls.Add(outBox, 0, 0);
        whereRow.Controls.Add(MakeButton("Browse...", delegate { BrowseOut(); }), 1, 0);
        Add(where, whereRow);

        // go
        var goRow = Row();
        goButton.Text = "Make videos";
        goButton.AutoSize = true;
        goButton.Padding = new Padding(10, 3, 10, 3);
        goButton.Font = new Font(Font, FontStyle.Bold);
        goButton.Click += delegate { Go(); };
        AcceptButton = goButton;
        cancelButton.Text = "Cancel";
        cancelButton.AutoSize = true;
        cancelButton.Click += delegate { Cancel(); };
        openButton.Text = "Open the folder";
        openButton.AutoSize = true;
        openButton.Click += delegate { OpenOut(); };
        goRow.Controls.Add(goButton);
        goRow.Controls.Add(cancelButton);
        goRow.Controls.Add(openButton);

        progress.Anchor = AnchorStyles.Left | AnchorStyles.Right;
        progress.Height = 18;
        status.AutoSize = true;
        status.Text = "Add some movies to get started.";
        status.Margin = new Padding(3, 6, 3, 3);
        detailsBox.Text = "Show details";
        detailsBox.AutoSize = true;
        detailsBox.CheckedChanged += delegate { log.Visible = detailsBox.Checked; };
        log.Multiline = true;
        log.ReadOnly = true;
        log.ScrollBars = ScrollBars.Both;
        log.WordWrap = false;
        log.Font = new Font(FontFamily.GenericMonospace, 8.5f);
        log.Dock = DockStyle.Fill;
        log.MinimumSize = new Size(0, 100);
        log.Visible = false;

        var rows = new Control[] { movies, style, make, where, goRow, progress, status, detailsBox, log };
        root.RowCount = rows.Length;
        for (int r = 0; r < rows.Length; r++)
        {
            root.RowStyles.Add(rows[r] == log ? new RowStyle(SizeType.Percent, 100) : new RowStyle(SizeType.AutoSize));
            root.Controls.Add(rows[r], 0, r);
        }
        root.Resize += delegate { status.MaximumSize = new Size(Math.Max(100, root.ClientSize.Width - 30), 0); };
    }

    // a titled box whose contents stack top to bottom and stretch to its width
    GroupBox Section(string title)
    {
        var g = new GroupBox { Text = title, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, Padding = new Padding(8, 4, 8, 6),
            Margin = new Padding(0, 0, 0, 10), Anchor = AnchorStyles.Left | AnchorStyles.Right };
        var inner = new TableLayoutPanel { ColumnCount = 1, Dock = DockStyle.Top, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink };
        inner.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        g.Controls.Add(inner);
        g.Tag = inner;
        return g;
    }

    static void Add(GroupBox g, Control c)
    {
        var inner = (TableLayoutPanel)g.Tag;
        inner.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        inner.Controls.Add(c, 0, inner.Controls.Count);
    }

    FlowLayoutPanel Row()
    {
        return new FlowLayoutPanel { FlowDirection = FlowDirection.LeftToRight, AutoSize = true, WrapContents = false, Margin = new Padding(0, 2, 0, 2) };
    }

    Button MakeButton(string text, EventHandler click)
    {
        var b = new Button { Text = text, AutoSize = true };
        b.Click += click;
        return b;
    }

    // ---- movies ---------------------------------------------------------
    void AddPath(string p)
    {
        if (Directory.Exists(p))
        {
            foreach (var f in Directory.GetFiles(p, "*.3mm", SearchOption.AllDirectories).OrderBy(x => x)) AddPath(f);
            return;
        }
        if (!File.Exists(p) || !p.EndsWith(".3mm", StringComparison.OrdinalIgnoreCase)) return;
        string full = Path.GetFullPath(p);
        foreach (MovieItem existing in movieList.Items) if (string.Equals(existing.Path, full, StringComparison.OrdinalIgnoreCase)) return;
        movieList.Items.Add(new MovieItem(full));
    }

    void AddMoviesDialog()
    {
        using (var d = new OpenFileDialog { Filter = "3D Movie Maker movies (*.3mm)|*.3mm", Multiselect = true, Title = "Add movies" })
            if (d.ShowDialog(this) == DialogResult.OK) { foreach (var f in d.FileNames) AddPath(f); UpdateButtons(); }
    }

    void AddFolderDialog()
    {
        using (var d = new FolderBrowserDialog { Description = "Add every movie in this folder (and the folders inside it)" })
            if (d.ShowDialog(this) == DialogResult.OK) { AddPath(d.SelectedPath); UpdateButtons(); }
    }

    void RemoveSelected()
    {
        if (proc != null) return;
        var sel = movieList.SelectedItems.Cast<object>().ToList();
        foreach (var o in sel) movieList.Items.Remove(o);
        UpdateButtons();
    }

    void OnDragEnter(object sender, DragEventArgs e)
    {
        e.Effect = (proc == null && e.Data.GetDataPresent(DataFormats.FileDrop)) ? DragDropEffects.Copy : DragDropEffects.None;
    }

    void OnDragDrop(object sender, DragEventArgs e)
    {
        var files = e.Data.GetData(DataFormats.FileDrop) as string[];
        if (files == null) return;
        foreach (var f in files) AddPath(f);
        UpdateButtons();
    }

    void BrowseOut()
    {
        using (var d = new FolderBrowserDialog { Description = "Save the videos in this folder", ShowNewFolderButton = true })
        {
            if (Directory.Exists(outBox.Text)) d.SelectedPath = outBox.Text;
            if (d.ShowDialog(this) == DialogResult.OK) outBox.Text = d.SelectedPath;
        }
    }

    void OpenOut()
    {
        string dir = outDir ?? outBox.Text;
        if (Directory.Exists(dir)) Process.Start("explorer.exe", "\"" + dir + "\"");
    }

    void UpdateButtons()
    {
        bool running = proc != null;
        bool anyMake = choices.Any(c => c.Box.Checked);
        goButton.Enabled = !running && movieList.Items.Count > 0 && anyMake;
        cancelButton.Enabled = running;
        openButton.Enabled = Directory.Exists(outDir ?? outBox.Text);
        foreach (var c in choices) c.Box.Enabled = !running;
        improved.Enabled = faithful.Enabled = outBox.Enabled = !running;
        if (!running && movieList.Items.Count > 0 && !anyMake) status.Text = "Tick at least one thing to make.";
        else if (!running && movieList.Items.Count > 0 && status.Text == "Add some movies to get started.")
            status.Text = movieList.Items.Count == 1 ? "Ready: 1 movie." : "Ready: " + movieList.Items.Count + " movies.";
    }

    // ---- running --------------------------------------------------------
    string Script(string name) { return Path.Combine(appDir, name); }

    bool ToolsReady()
    {
        string tools = Path.Combine(appDir, "tools");
        bool fluid = Directory.Exists(tools) && Directory.GetFiles(tools, "fluidsynth.exe", SearchOption.AllDirectories).Length > 0;
        bool sf = File.Exists(Path.Combine(tools, "GeneralUser-GS.sf2"));
        bool ff = (Directory.Exists(tools) && Directory.GetFiles(tools, "ffmpeg.exe", SearchOption.AllDirectories).Length > 0) || OnPath("ffmpeg.exe");
        return fluid && sf && ff;
    }

    static bool OnPath(string exe)
    {
        foreach (var d in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
        {
            try { if (d.Length > 0 && File.Exists(Path.Combine(d.Trim(), exe))) return true; } catch { }
        }
        return false;
    }

    void Go()
    {
        if (proc != null || !goButton.Enabled) return;
        if (!File.Exists(Script("render-folder.ps1")))
        {
            Fail("render-folder.ps1 should be next to McZeesCut.exe. Unzip the whole download and run it from there.");
            return;
        }
        outDir = outBox.Text.Trim();
        try { Directory.CreateDirectory(outDir); }
        catch (Exception ex) { Fail("Can't save to that folder: " + ex.Message); return; }

        // the script converts a folder, so copy the chosen movies into one
        stageDir = Path.Combine(Path.GetTempPath(), "McZeesCut-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(stageDir);
        var used = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (MovieItem m in movieList.Items)
        {
            string f = m.Path;
            string name = Path.GetFileNameWithoutExtension(f);
            string pick = name;
            for (int k = 2; used.Contains(pick); k++) pick = name + " (" + k + ")";
            used.Add(pick);
            try { File.Copy(f, Path.Combine(stageDir, pick + ".3mm")); }
            catch (Exception ex) { Fail("Can't read " + f + ": " + ex.Message); return; }
        }
        cancelled = false;
        log.Clear();
        progress.Value = 0;
        needsSetup = !ToolsReady();
        if (needsSetup)
        {
            SetStatus("Getting ready (first time only): downloading ffmpeg and music instruments, about 200 MB...");
            progress.Style = ProgressBarStyle.Marquee;
            Run(Script("get-tools.ps1"), "", delegate (int code)
            {
                progress.Style = ProgressBarStyle.Continuous;
                if (cancelled) { Finish(); return; }
                if (code != 0 || !ToolsReady()) { Fail("Couldn't download the tools it needs. Check the internet connection and try again (details below)."); ShowDetails(); Finish(); return; }
                StartRender();
            });
        }
        else StartRender();
    }

    void StartRender()
    {
        var formats = choices.Where(c => c.Box.Checked && c.Format != null).Select(c => c.Format).ToList();
        var a = new StringBuilder();
        a.Append(" -InputDir ").Append(Quote(stageDir));
        a.Append(" -OutputDir ").Append(Quote(outDir));
        a.Append(" -Formats ").Append(formats.Count > 0 ? string.Join(",", formats) : "none");
        if (improved.Checked) a.Append(" -Smooth -Duck");
        if (choices.First(c => c.Key == "sounds").Box.Checked) a.Append(" -ExtractSounds");
        a.Append(" -Force");
        SetStatus("Starting...");
        Run(Script("render-folder.ps1"), a.ToString(), delegate (int code) { Done(code); });
    }

    static string Quote(string s) { return "\"" + s.TrimEnd('\\') + "\""; }

    void Run(string script, string args, Action<int> onExit)
    {
        var psi = new ProcessStartInfo("powershell.exe",
            "-NoProfile -ExecutionPolicy Bypass -File " + Quote(script) + args)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = appDir,
        };
        AppendLog("> " + Path.GetFileName(script) + args);
        proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (s, e) => { if (e.Data != null) BeginInvoke(new Action(() => OnLine(e.Data))); };
        proc.ErrorDataReceived += (s, e) => { if (e.Data != null) BeginInvoke(new Action(() => AppendLog(e.Data))); };
        proc.Exited += (s, e) =>
        {
            int code = 0;
            try { code = proc.ExitCode; } catch { }
            BeginInvoke(new Action(() => { proc = null; onExit(code); UpdateButtons(); }));
        };
        try
        {
            proc.Start();
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
        }
        catch (Exception ex)
        {
            proc = null;
            Fail("Couldn't start PowerShell: " + ex.Message);
            Finish();
        }
        UpdateButtons();
    }

    void OnLine(string line)
    {
        AppendLog(line);
        // render-folder.ps1 prints "[3/7] Movie.3mm" as it starts each movie
        if (line.StartsWith("[") && line.Contains("/") && line.Contains("]"))
        {
            int close = line.IndexOf(']');
            var parts = line.Substring(1, close - 1).Split('/');
            int i, n;
            if (parts.Length == 2 && int.TryParse(parts[0], out i) && int.TryParse(parts[1], out n) && n > 0)
            {
                string name = line.Substring(close + 1).Trim();
                if (name.EndsWith(".3mm", StringComparison.OrdinalIgnoreCase)) name = name.Substring(0, name.Length - 4);
                progress.Value = Math.Min(100, 100 * (i - 1) / n);
                SetStatus(n == 1 ? "Making " + name + "..." : "Making " + i + " of " + n + ": " + name + "...");
            }
        }
        else if (needsSetup && line.StartsWith("Downloading")) SetStatus("Getting ready (first time only): " + line);
    }

    void Done(int code)
    {
        progress.Value = 100;
        if (cancelled) { SetStatus("Stopped."); Finish(); return; }
        // report.csv: one row per movie, with a status
        var problems = new List<string>();
        int ok = 0;
        string report = Path.Combine(outDir, "report.csv");
        if (File.Exists(report))
        {
            foreach (var row in File.ReadAllLines(report).Skip(1))
            {
                var cols = SplitCsv(row);
                if (cols.Count < 2) continue;
                string movie = Path.GetFileNameWithoutExtension(cols[0]);
                string st = cols[1];
                if (st == "ok") ok++;
                else if (st == "missing-content")
                    problems.Add(movie + " uses 3D Movie Maker add-on content that isn't included" + (cols.Count > 5 && cols[5] != "" ? " (" + cols[5] + ")" : "") + ".");
                else problems.Add(movie + " couldn't be converted (" + st + ").");
            }
        }
        else problems.Add("Something went wrong before any movie was converted.");

        if (problems.Count == 0)
        {
            SetStatus(ok == 1 ? "Done! Your video is in " + outDir : "Done! All " + ok + " videos are in " + outDir);
        }
        else
        {
            ExitCode = 1;
            SetStatus((ok > 0 ? ok + " done. " : "") + string.Join(" ", problems.ToArray()) + " Details below.");
            ShowDetails();
        }
        Finish();
    }

    void Finish()
    {
        try { if (stageDir != null && Directory.Exists(stageDir)) Directory.Delete(stageDir, true); } catch { }
        stageDir = null;
        UpdateButtons();
        if (screenshot != null) SaveScreenshot(Path.ChangeExtension(screenshot, null) + "-done.png");
        if (closeWhenDone) Close();
    }

    void Cancel()
    {
        if (proc == null) return;
        cancelled = true;
        SetStatus("Stopping...");
        try
        {
            // the script starts the renderer and ffmpeg; stop all of them
            var k = Process.Start(new ProcessStartInfo("taskkill", "/T /F /PID " + proc.Id) { CreateNoWindow = true, UseShellExecute = false });
            if (k != null) k.WaitForExit(5000);
        }
        catch { }
    }

    void OnClosing(object sender, FormClosingEventArgs e)
    {
        if (proc == null) return;
        if (!closeWhenDone && MessageBox.Show(this, "Videos are still being made. Stop and close?", "McZee's Cut",
                MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
        {
            e.Cancel = true;
            return;
        }
        closeWhenDone = false;
        Cancel();
        try { if (stageDir != null) Directory.Delete(stageDir, true); } catch { }
    }

    void Fail(string message)
    {
        ExitCode = 1;
        SetStatus(message);
        if (!autoGo) MessageBox.Show(this, message, "McZee's Cut", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        AppendLog(message);
    }

    void SetStatus(string s) { status.Text = s; }

    void ShowDetails() { detailsBox.Checked = true; }

    void AppendLog(string s)
    {
        log.AppendText(s + Environment.NewLine);
    }

    static List<string> SplitCsv(string line)
    {
        var cols = new List<string>();
        var cur = new StringBuilder();
        bool q = false;
        for (int i = 0; i < line.Length; i++)
        {
            char ch = line[i];
            if (q)
            {
                if (ch == '"' && i + 1 < line.Length && line[i + 1] == '"') { cur.Append('"'); i++; }
                else if (ch == '"') q = false;
                else cur.Append(ch);
            }
            else if (ch == '"') q = true;
            else if (ch == ',') { cols.Add(cur.ToString()); cur.Clear(); }
            else cur.Append(ch);
        }
        cols.Add(cur.ToString());
        return cols;
    }

    // ---- command line ---------------------------------------------------
    void ParseArgs(string[] args)
    {
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i];
            string next = i + 1 < args.Length ? args[i + 1] : null;
            if (a == "--out" && next != null) { outBox.Text = next; i++; }
            else if (a == "--style" && next != null) { (next == "faithful" ? faithful : improved).Checked = true; i++; }
            else if (a == "--make" && next != null)
            {
                var want = next.Split(',').Select(x => x.Trim()).ToList();
                foreach (var c in choices) c.Box.Checked = want.Contains(c.Key);
                i++;
            }
            else if (a == "--go") autoGo = true;
            else if (a == "--close-when-done") closeWhenDone = true;
            else if (a == "--screenshot" && next != null) { screenshot = Path.GetFullPath(next); i++; }
            else AddPath(a);
        }
    }

    void SaveScreenshot(string path)
    {
        try
        {
            using (var bmp = new Bitmap(Width, Height))
            {
                DrawToBitmap(bmp, new Rectangle(0, 0, Width, Height));
                bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            }
        }
        catch (Exception ex) { AppendLog("screenshot failed: " + ex.Message); }
    }
}

// a movie in the list: shows its name, remembers where it is
class MovieItem
{
    public readonly string Path;
    public MovieItem(string path) { Path = path; }
    public override string ToString()
    {
        string dir = System.IO.Path.GetFileName(System.IO.Path.GetDirectoryName(Path));
        return System.IO.Path.GetFileNameWithoutExtension(Path) + (string.IsNullOrEmpty(dir) ? "" : "   (in " + dir + ")");
    }
}
