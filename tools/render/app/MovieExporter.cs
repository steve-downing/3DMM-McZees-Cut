// Movie Exporter: McZee's Cut's small Windows app around render-folder.ps1,
// for people who would rather not use the command line. Pick movies, pick a
// style, pick what to make, press the button. 3D Movie Maker's Export button
// runs it too, for one movie at a time.
//
// Built with the C# compiler that ships with Windows (.NET Framework 4.x), so
// it sticks to C# 5. It lives next to render-folder.ps1 in the package.
//
// Command line (all optional):
//   "Movie Exporter.exe" [movie.3mm | folder]... [--out <folder>] [--style improved|faithful]
//                 [--make mp4,crt,sbs,hsbs,anaglyph,avi,sounds] [--go] [--close-when-done]
//                 [--screenshot <file.png>]
//       the full window, filled in (CI uses --go --close-when-done)
//   "Movie Exporter.exe" --export <movie.3mm> --to <file> --preset avi|faithful|faithful-crt|improved
//                 [--close-when-done] [--screenshot <file.png>]
//       a small window that exports one movie to one file (3DMM's Export button)
//   "Movie Exporter.exe" --prefetch
//       no window: download ffmpeg and anything else missing, then exit
//       (3DMM starts this as soon as Export is clicked)
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

static class Program
{
    [DllImport("user32.dll")]
    static extern bool SetProcessDPIAware();

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Contains("--prefetch")) return Tools.Ensure(null) ? 0 : 1;
        try { SetProcessDPIAware(); } catch { }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        if (args.Contains("--export"))
        {
            var ef = new ExportForm(args);
            if (ef.Headless) return ef.RunHeadless();
            Application.Run(ef);
            return ef.ExitCode;
        }
        var form = new MainForm(args);
        Application.Run(form);
        return form.ExitCode;
    }
}

// ffmpeg, FluidSynth and the instruments, in .\tools (get-tools.ps1 fetches
// what's missing). Shared by every Movie Exporter process: a named mutex makes
// a second download wait for the first instead of fighting over the files.
static class Tools
{
    public static readonly string AppDir = AppDomain.CurrentDomain.BaseDirectory;
    static Process current;

    public static string Script(string name) { return Path.Combine(AppDir, name); }

    public static string Quote(string s) { return "\"" + s.TrimEnd('\\') + "\""; }

    public static bool Ready()
    {
        string tools = Path.Combine(AppDir, "tools");
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

    // Blocks until the tools are there (downloading them if needed), so call
    // it from a background thread. onLine gets get-tools.ps1's output.
    public static bool Ensure(Action<string> onLine)
    {
        using (var m = new Mutex(false, @"Local\McZeesCut-MovieExporter-tools"))
        {
            try { m.WaitOne(); } catch (AbandonedMutexException) { }
            try
            {
                if (Ready()) return true;
                var psi = new ProcessStartInfo("powershell.exe",
                    "-NoProfile -ExecutionPolicy Bypass -File " + Quote(Script("get-tools.ps1")))
                {
                    UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = AppDir,
                    RedirectStandardOutput = true, RedirectStandardError = true,
                };
                using (var p = Process.Start(psi))
                {
                    current = p;
                    p.ErrorDataReceived += (s, e) => { if (e.Data != null && onLine != null) onLine(e.Data); };
                    p.BeginErrorReadLine();
                    string line;
                    while ((line = p.StandardOutput.ReadLine()) != null) if (onLine != null) onLine(line);
                    p.WaitForExit();
                    current = null;
                }
                return Ready();
            }
            catch (Exception ex)
            {
                if (onLine != null) onLine("couldn't run get-tools.ps1: " + ex.Message);
                return false;
            }
            finally { m.ReleaseMutex(); }
        }
    }

    // 3D Movie Maker may still have the movie open: copy it without asking
    // for exclusive access
    public static void CopyShared(string from, string to)
    {
        using (var src = new FileStream(from, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        using (var dst = new FileStream(to, FileMode.CreateNew, FileAccess.Write))
            src.CopyTo(dst);
    }

    public static void StopDownload()
    {
        try { var p = current; if (p != null && !p.HasExited) Kill(p.Id); } catch { }
    }

    // stops a process and everything it started (the renderer, ffmpeg)
    public static void Kill(int pid)
    {
        try
        {
            var k = Process.Start(new ProcessStartInfo("taskkill", "/T /F /PID " + pid) { CreateNoWindow = true, UseShellExecute = false });
            if (k != null) k.WaitForExit(5000);
        }
        catch { }
    }

    // report.csv from render-folder.ps1: one row per movie
    public static List<List<string>> ReadReport(string file)
    {
        var rows = new List<List<string>>();
        if (!File.Exists(file)) return rows;
        foreach (var row in File.ReadAllLines(file).Skip(1)) rows.Add(SplitCsv(row));
        return rows;
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

    // a problem with one movie, in plain words; null when it worked
    public static string Problem(List<string> cols)
    {
        if (cols.Count < 2 || cols[1] == "ok") return null;
        string movie = Path.GetFileNameWithoutExtension(cols[0]);
        if (cols[1] == "missing-content")
            return movie + " uses 3D Movie Maker add-on content that isn't included" + (cols.Count > 5 && cols[5] != "" ? " (" + cols[5] + ")" : "") + ".";
        return movie + " couldn't be converted (" + cols[1] + ").";
    }

    public static void SaveScreenshot(Form f, string path)
    {
        try
        {
            using (var bmp = new Bitmap(f.Width, f.Height))
            {
                f.DrawToBitmap(bmp, new Rectangle(0, 0, f.Width, f.Height));
                bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            }
        }
        catch { }
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

    readonly string appDir = Tools.AppDir;
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
        // two columns: 2-D on the left, 3D on the right
        new Choice("mp4", "2d", "Video (MP4)",
            "The movie as a regular video file that plays on anything.", true),
        new Choice("crt", "crt", "90s monitor look (4K MP4)",
            "The movie as it looked on a mid-90s computer screen: scanlines, glowing phosphors. A large 4K file.", false),
        new Choice("avi", "avi", "Windows 95/98 video (AVI)",
            "A small video that plays on an old Windows 95 or 98 PC with nothing extra installed.", false),
        new Choice("sounds", null, "The movie's sounds (ZIP)",
            "The voices, sound effects and music added to the movie, as audio files.", false),
        new Choice("sbs", "sbs", "3D for VR headsets (MP4)",
            "Real 3D: a full picture for each eye, side by side. For VR video players and YouTube.", false),
        new Choice("hsbs", "hsbs", "3D for 3D TVs (MP4)",
            "Real 3D for a 3D TV or monitor: both pictures squeezed into one HD frame. Turn on the TV's side-by-side 3D mode.", false),
        new Choice("anaglyph", "anaglyph", "3D for red/cyan glasses (MP4)",
            "3D you can watch on any screen with red/cyan paper glasses.", false),
    };

    Process proc;
    string stageDir;
    string outDir;
    bool cancelled;
    bool autoGo, closeWhenDone;
    string screenshot;
    bool waitingForTools;

    public MainForm(string[] args)
    {
        Text = "Movie Exporter";
        AutoScaleDimensions = new SizeF(96f, 96f);   // laid out at 100%; scaled up on high-DPI screens
        AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 9f);
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(560, 480);
        Size = new Size(660, 660);
        AllowDrop = true;
        BuildLayout();
        outBox.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyVideos), "3D Movie Maker");
        ParseArgs(args);
        UpdateButtons();
        DragEnter += OnDragEnter;
        DragDrop += OnDragDrop;
        FormClosing += OnClosing;
        Shown += delegate
        {
            if (screenshot != null) SaveScreenshot(screenshot);
            // the first time, start fetching ffmpeg right away, while movies are being picked
            if (!autoGo && !Tools.Ready()) EnsureTools(null);
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
        bool running = proc != null || stageDir != null;
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
    string Script(string name) { return Tools.Script(name); }

    // Runs then() on the UI thread once the tools are there; a download
    // started earlier (by this window or another process) is waited for.
    void EnsureTools(Action then)
    {
        bool ready = Tools.Ready();
        if (!ready)
        {
            waitingForTools = true;
            progress.Style = ProgressBarStyle.Marquee;
            SetStatus(then == null
                ? "Getting ready in the background (first time only): downloading ffmpeg..."
                : "Finishing the one-time download of ffmpeg first...");
        }
        UpdateButtons();
        var t = new Thread(() =>
        {
            bool ok = ready || Tools.Ensure(line => BeginInvoke(new Action(() => AppendLog(line))));
            BeginInvoke(new Action(() =>
            {
                waitingForTools = false;
                progress.Style = ProgressBarStyle.Continuous;
                if (!ok)
                {
                    if (then != null && !cancelled) { Fail("Couldn't download ffmpeg. Check the internet connection and try again (details below)."); ShowDetails(); Finish(); }
                    else if (then == null) SetStatus("Couldn't download ffmpeg yet. It will try again when you make videos.");
                    UpdateButtons();
                    return;
                }
                if (then == null)
                {
                    if (proc == null && stageDir == null) SetStatus(movieList.Items.Count > 0 ? "Ready." : "Ready. Add some movies to get started.");
                    UpdateButtons();
                    return;
                }
                if (cancelled) { SetStatus("Stopped."); Finish(); return; }
                then();
            }));
        });
        t.IsBackground = true;
        t.Start();
    }

    void Go()
    {
        if (proc != null || stageDir != null || !goButton.Enabled) return;
        if (!File.Exists(Script("render-folder.ps1")))
        {
            Fail("render-folder.ps1 should be next to Movie Exporter.exe. Unzip the whole download and run it from there.");
            return;
        }
        outDir = outBox.Text.Trim();
        try { Directory.CreateDirectory(outDir); }
        catch (Exception ex) { Fail("Can't save to that folder: " + ex.Message); return; }

        // the script converts a folder, so copy the chosen movies into one
        stageDir = Path.Combine(Path.GetTempPath(), "MovieExporter-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(stageDir);
        var used = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (MovieItem m in movieList.Items)
        {
            string f = m.Path;
            string name = Path.GetFileNameWithoutExtension(f);
            string pick = name;
            for (int k = 2; used.Contains(pick); k++) pick = name + " (" + k + ")";
            used.Add(pick);
            try { Tools.CopyShared(f, Path.Combine(stageDir, pick + ".3mm")); }
            catch (Exception ex) { Fail("Can't read " + f + ": " + ex.Message); Finish(); return; }
        }
        cancelled = false;
        log.Clear();
        progress.Value = 0;
        EnsureTools(StartRender);
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

    static string Quote(string s) { return Tools.Quote(s); }

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
        else if (waitingForTools && line.StartsWith("Downloading")) SetStatus("Getting ready (first time only): " + line);
    }

    void Done(int code)
    {
        progress.Value = 100;
        if (cancelled) { SetStatus("Stopped."); Finish(); return; }
        // report.csv: one row per movie, with a status
        var problems = new List<string>();
        int ok = 0;
        var rows = Tools.ReadReport(Path.Combine(outDir, "report.csv"));
        foreach (var cols in rows)
        {
            string p = Tools.Problem(cols);
            if (p == null) ok++; else problems.Add(p);
        }
        if (rows.Count == 0) problems.Add("Something went wrong before any movie was converted.");

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
        if (proc == null && stageDir == null) return;
        cancelled = true;
        SetStatus("Stopping...");
        if (proc != null) Tools.Kill(proc.Id);   // the script, the renderer and ffmpeg
    }

    void OnClosing(object sender, FormClosingEventArgs e)
    {
        if (proc == null && stageDir == null) return;
        if (!closeWhenDone && MessageBox.Show(this, "Videos are still being made. Stop and close?", "Movie Exporter",
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
        if (!autoGo) MessageBox.Show(this, message, "Movie Exporter", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        AppendLog(message);
    }

    void SetStatus(string s) { status.Text = s; }

    void ShowDetails() { detailsBox.Checked = true; }

    void AppendLog(string s)
    {
        log.AppendText(s + Environment.NewLine);
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

// One movie to one file, for 3D Movie Maker's Export button: a small window
// with a progress bar that keeps going while you carry on in 3DMM.
class ExportForm : Form
{
    public int ExitCode = 0;

    string movie, target, preset = "improved", screenshot;
    bool closeWhenDone, cancelled, finished;
    Process proc;
    string work;

    // Launched by 3D Movie Maker (--notify <its window>): no window of our
    // own, so 3DMM keeps the focus. Progress goes to 3DMM, which shows it;
    // we close when done.
    IntPtr notify = IntPtr.Zero;
    public bool Headless { get { return notify != IntPtr.Zero; } }
    string ffProgress;
    double renderShare = 0.75, durationMs, renderPct;
    bool encoding;
    int lastPct = -1;
    string lastState, lastText;
    readonly System.Windows.Forms.Timer poll = new System.Windows.Forms.Timer { Interval = 500 };

    readonly Label title = new Label();
    readonly Label detail = new Label();
    readonly ProgressBar progress = new ProgressBar();
    readonly Label status = new Label();
    readonly Button watchButton = new Button();
    readonly Button showButton = new Button();
    readonly Button closeButton = new Button();
    readonly CheckBox detailsBox = new CheckBox();
    readonly TextBox log = new TextBox();

    static readonly Dictionary<string, string> PresetNames = new Dictionary<string, string>
    {
        { "avi", "AVI for Windows 95 and 98" },
        { "faithful", "MP4, faithful" },
        { "faithful-crt", "MP4, faithful, 90s monitor look" },
        { "improved", "MP4, improved: smooth motion, music dips while characters talk" },
    };

    public ExportForm(string[] args)
    {
        for (int i = 0; i < args.Length; i++)
        {
            string next = i + 1 < args.Length ? args[i + 1] : null;
            if (args[i] == "--export" && next != null) { movie = next; i++; }
            else if (args[i] == "--to" && next != null) { target = next; i++; }
            else if (args[i] == "--preset" && next != null) { preset = next; i++; }
            else if (args[i] == "--close-when-done") closeWhenDone = true;
            else if (args[i] == "--screenshot" && next != null) { screenshot = Path.GetFullPath(next); i++; }
            else if (args[i] == "--notify" && next != null)
            {
                long h;
                if (long.TryParse(next, out h)) notify = new IntPtr(h);
                i++;
            }
        }
        if (preset == "faithful-crt") renderShare = 0.3;   // the 4K CRT encode is most of the work
        poll.Tick += delegate { PollEncode(); };
        if (!PresetNames.ContainsKey(preset)) preset = "improved";
        if (target == null && movie != null)
            target = Path.ChangeExtension(movie, preset == "avi" ? ".avi" : ".mp4");

        string name = movie != null ? Path.GetFileNameWithoutExtension(movie) : "?";
        Text = "Exporting " + name;
        AutoScaleDimensions = new SizeF(96f, 96f);
        AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 9f);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        TopMost = true;   // stay visible over 3D Movie Maker
        ClientSize = new Size(440, 170);

        var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, Padding = new Padding(12) };
        root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        Controls.Add(root);
        title.Text = "Exporting “" + name + "”";
        title.Font = new Font(Font.FontFamily, 11f, FontStyle.Bold);
        title.AutoSize = true;
        detail.Text = PresetNames[preset] + "\nto " + target;
        detail.AutoSize = true;
        detail.MaximumSize = new Size(410, 0);
        detail.ForeColor = SystemColors.GrayText;
        progress.Style = ProgressBarStyle.Marquee;
        progress.Anchor = AnchorStyles.Left | AnchorStyles.Right;
        progress.Height = 16;
        status.AutoSize = true;
        status.MaximumSize = new Size(410, 0);
        status.Text = "Starting...";
        var buttons = new FlowLayoutPanel { AutoSize = true, WrapContents = false, Margin = new Padding(0, 6, 0, 0) };
        watchButton.Text = "Watch it";
        showButton.Text = "Show in folder";
        closeButton.Text = "Cancel";
        foreach (var b in new[] { watchButton, showButton, closeButton }) { b.AutoSize = true; buttons.Controls.Add(b); }
        watchButton.Visible = showButton.Visible = false;
        watchButton.Click += delegate { try { Process.Start(target); } catch { } };
        showButton.Click += delegate { try { Process.Start("explorer.exe", "/select,\"" + target + "\""); } catch { } };
        closeButton.Click += delegate { Close(); };
        detailsBox.Text = "Show details";
        detailsBox.AutoSize = true;
        detailsBox.CheckedChanged += delegate
        {
            log.Visible = detailsBox.Checked;
            ClientSize = new Size(ClientSize.Width, detailsBox.Checked ? 360 : 170);
        };
        log.Multiline = true;
        log.ReadOnly = true;
        log.ScrollBars = ScrollBars.Both;
        log.WordWrap = false;
        log.Font = new Font(FontFamily.GenericMonospace, 8.5f);
        log.Dock = DockStyle.Fill;
        log.Visible = false;
        var rows = new Control[] { title, detail, progress, status, buttons, detailsBox, log };
        root.RowCount = rows.Length;
        for (int r = 0; r < rows.Length; r++)
        {
            root.RowStyles.Add(rows[r] == log ? new RowStyle(SizeType.Percent, 100) : new RowStyle(SizeType.AutoSize));
            root.Controls.Add(rows[r], 0, r);
        }

        FormClosing += OnClosing;
        Shown += delegate
        {
            if (screenshot != null) Tools.SaveScreenshot(this, screenshot);
            Start();
        };
    }

    void Log(string line) { log.AppendText(line + Environment.NewLine); }

    void Start()
    {
        if (movie == null || !File.Exists(movie)) { Fail("Can't find the movie to export: " + movie); return; }
        if (!File.Exists(Tools.Script("render-folder.ps1"))) { Fail("render-folder.ps1 should be next to Movie Exporter.exe."); return; }

        // render-folder.ps1 converts a folder: give it a folder with just this movie
        work = Path.Combine(Path.GetTempPath(), "MovieExporter-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        string inDir = Path.Combine(work, "in");
        Directory.CreateDirectory(inDir);
        try { Tools.CopyShared(movie, Path.Combine(inDir, "movie.3mm")); }
        catch (Exception ex) { Fail("Can't read the movie: " + ex.Message); return; }

        Report(0, "Exporting " + ShortName());
        if (!Tools.Ready()) { status.Text = "Getting ready (first time only): downloading ffmpeg..."; Report(0, "Getting ready to export"); }
        var t = new Thread(() =>
        {
            bool ok = Tools.Ensure(line => BeginInvoke(new Action(() =>
            {
                Log(line);
                if (line.StartsWith("Downloading")) status.Text = "Getting ready (first time only): " + line;
            })));
            BeginInvoke(new Action(() =>
            {
                if (cancelled) return;
                if (!ok) { Fail("Couldn't download ffmpeg. Check the internet connection and try again."); return; }
                Render();
            }));
        });
        t.IsBackground = true;
        t.Start();
    }

    void Render()
    {
        string outDir = Path.Combine(work, "out");
        string formats = preset == "avi" ? "avi" : preset == "faithful-crt" ? "crt" : "2d";
        ffProgress = Path.Combine(work, "ffmpeg-progress.txt");
        string args = " -InputDir " + Tools.Quote(Path.Combine(work, "in")) + " -OutputDir " + Tools.Quote(outDir) +
                      " -Formats " + formats + (preset == "improved" ? " -Smooth -Duck" : "") + " -Force" +
                      " -Progress -ProgressFile " + Tools.Quote(ffProgress);
        status.Text = preset == "faithful-crt" ? "Making the video (the 4K CRT look takes a while)..." : "Making the video...";
        Log("> render-folder.ps1" + args);
        var psi = new ProcessStartInfo("powershell.exe", "-NoProfile -ExecutionPolicy Bypass -File " + Tools.Quote(Tools.Script("render-folder.ps1")) + args)
        {
            UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Tools.AppDir,
            RedirectStandardOutput = true, RedirectStandardError = true,
        };
        proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (s, e) => { if (e.Data != null) BeginInvoke(new Action(() => OnLine(e.Data))); };
        proc.ErrorDataReceived += (s, e) => { if (e.Data != null) BeginInvoke(new Action(() => Log(e.Data))); };
        proc.Exited += (s, e) => BeginInvoke(new Action(() => { proc = null; poll.Stop(); Done(outDir); }));
        Report(0, "Exporting " + ShortName());
        try { proc.Start(); proc.BeginOutputReadLine(); proc.BeginErrorReadLine(); poll.Start(); }
        catch (Exception ex) { proc = null; Fail("Couldn't start PowerShell: " + ex.Message); }
    }

    void Done(string outDir)
    {
        if (cancelled) { Cleanup(); return; }
        string made = Path.Combine(outDir, preset == "avi" ? "movie.avi" : preset == "faithful-crt" ? "movie.crt.mp4" : "movie.mp4");
        if (!File.Exists(made))
        {
            string why = null;
            foreach (var cols in Tools.ReadReport(Path.Combine(outDir, "report.csv"))) why = why ?? Tools.Problem(cols);
            Fail((why ?? "The video wasn't made.").Replace("movie ", "The movie ") + " Details below.");
            return;
        }
        try
        {
            string dir = Path.GetDirectoryName(Path.GetFullPath(target));
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            if (File.Exists(target)) File.Delete(target);
            File.Move(made, target);
        }
        catch (Exception ex) { Fail("Couldn't save " + target + ": " + ex.Message); return; }
        finished = true;
        progress.Style = ProgressBarStyle.Continuous;
        progress.Value = 100;
        status.Text = "Done!";
        Notify("done", 100, "Saved " + Shorten(Path.GetFileName(target), 26));
        if (Headless) { Cleanup(); ExitLater(6000); return; }
        watchButton.Visible = showButton.Visible = true;
        closeButton.Text = "Close";
        Cleanup();
        if (screenshot != null) Tools.SaveScreenshot(this, Path.ChangeExtension(screenshot, null) + "-done.png");
        if (closeWhenDone) Close();
    }

    void Fail(string message)
    {
        ExitCode = 1;
        finished = true;
        progress.Style = ProgressBarStyle.Continuous;
        progress.Value = 0;
        status.Text = message;
        status.ForeColor = Color.Firebrick;
        if (Headless)
        {
            Log(message);
            SaveLog();
            Notify("fail", 0, "Export didn't work: " + Shorten(message, 44));
            Cleanup();
            ExitLater(20000);
            return;
        }
        closeButton.Text = "Close";
        Log(message);
        detailsBox.Checked = true;
        Cleanup();
        if (screenshot != null) Tools.SaveScreenshot(this, Path.ChangeExtension(screenshot, null) + "-done.png");
        if (closeWhenDone) Close();
    }

    // ---- progress -------------------------------------------------------

    string ShortName()
    {
        return Shorten(movie != null ? Path.GetFileNameWithoutExtension(movie) : "your movie", 22);
    }

    static string Shorten(string s, int n) { return s.Length <= n ? s : s.Substring(0, n - 1) + "…"; }

    // a line from render-folder.ps1: its "@" lines are progress
    void OnLine(string line)
    {
        double v;
        if (line.StartsWith("@progress render ") && double.TryParse(line.Substring(17), out v))
        {
            renderPct = v;
            Report((int)(v * renderShare), "Exporting " + ShortName());
            return;
        }
        if (line.StartsWith("@duration_ms ") && double.TryParse(line.Substring(13), out v)) { durationMs = v; encoding = true; return; }
        Log(line);
    }

    // ffmpeg's -progress reports: how far into the video the encode is
    void PollEncode()
    {
        if (!encoding || durationMs <= 0 || ffProgress == null) return;
        try
        {
            string text;
            using (var fs = new FileStream(ffProgress, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (var r = new StreamReader(fs)) text = r.ReadToEnd();
            int i = text.LastIndexOf("out_time_us=", StringComparison.Ordinal);
            if (i < 0) return;
            int j = text.IndexOf('\n', i);
            long us;
            if (!long.TryParse((j < 0 ? text.Substring(i + 12) : text.Substring(i + 12, j - i - 12)).Trim(), out us)) return;
            double f = Math.Max(0, Math.Min(1, us / 1000.0 / durationMs));
            Report((int)(100 * renderShare + f * 100 * (0.99 - renderShare)), "Exporting " + ShortName());
        }
        catch { }
    }

    void Report(int pct, string text)
    {
        pct = Math.Max(0, Math.Min(100, pct));
        if (pct < lastPct && text == lastText) return;   // never go backwards
        if (progress.Style != ProgressBarStyle.Continuous && pct > 0) progress.Style = ProgressBarStyle.Continuous;
        progress.Value = pct;
        Notify("run", pct, text);
    }

    [StructLayout(LayoutKind.Sequential)]
    struct COPYDATASTRUCT { public IntPtr dwData; public int cbData; public IntPtr lpData; }

    [DllImport("user32.dll", CharSet = CharSet.Ansi)]
    static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint msg, IntPtr wParam, ref COPYDATASTRUCT lParam, uint flags, uint timeout, out IntPtr result);

    // Tells 3D Movie Maker how the export is going: WM_COPYDATA, tagged MZEX,
    // with "<our process id> <run|done|fail|hide> <percent> <text>"
    void Notify(string state, int pct, string text)
    {
        if (!Headless) return;
        if (state == lastState && pct == lastPct && text == lastText) return;
        lastState = state; lastPct = pct; lastText = text;
        byte[] b = Encoding.Default.GetBytes(Process.GetCurrentProcess().Id + " " + state + " " + pct + " " + text + "\0");
        IntPtr p = Marshal.AllocHGlobal(b.Length);
        try
        {
            Marshal.Copy(b, 0, p, b.Length);
            var cds = new COPYDATASTRUCT { dwData = new IntPtr(0x58455A4D), cbData = b.Length, lpData = p };
            IntPtr result;
            SendMessageTimeout(notify, 0x004A /* WM_COPYDATA */, IntPtr.Zero, ref cds, 0x0002 /* SMTO_ABORTIFHUNG */, 2000, out result);
        }
        catch { }
        finally { Marshal.FreeHGlobal(p); }
    }

    // keep the result up in 3DMM for a moment, then take it down and quit
    void ExitLater(int ms)
    {
        var t = new System.Windows.Forms.Timer { Interval = ms };
        t.Tick += delegate { t.Stop(); Notify("hide", 100, ""); Application.ExitThread(); };
        t.Start();
    }

    // when 3DMM launched us, a failed export leaves its details here
    string SaveLog()
    {
        try
        {
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "McZee's Cut");
            Directory.CreateDirectory(dir);
            string path = Path.Combine(dir, "Export log.txt");
            File.WriteAllText(path, "Exporting " + movie + "\r\nto " + target + " (" + preset + ")\r\n\r\n" + log.Text);
            return path;
        }
        catch { return null; }
    }

    public int RunHeadless()
    {
        IntPtr unused = Handle;   // a window handle (never shown) to receive our own callbacks
        Application.ThreadException += (s, e) => { Notify("fail", 0, "Export didn't work: " + Shorten(e.Exception.Message, 60)); Notify("hide", 0, ""); Application.ExitThread(); };
        AppDomain.CurrentDomain.UnhandledException += (s, e) => Notify("hide", 0, "");
        BeginInvoke(new Action(Start));
        Application.Run();
        return ExitCode;
    }

    void Cleanup()
    {
        try { if (work != null && Directory.Exists(work)) Directory.Delete(work, true); } catch { }
        work = null;
    }

    void OnClosing(object sender, FormClosingEventArgs e)
    {
        if (finished) return;
        if (!closeWhenDone && MessageBox.Show(this, "Stop exporting?", Text, MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
        {
            e.Cancel = true;
            return;
        }
        cancelled = true;
        ExitCode = 1;
        if (proc != null) Tools.Kill(proc.Id);
        Cleanup();
    }
}

