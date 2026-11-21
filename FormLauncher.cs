using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class FormLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        string folder = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(folder, @"runtime\python.exe");
        if (!File.Exists(python)) python = Path.Combine(folder, @"dist\FormStudio\runtime\python.exe");
        if (!File.Exists(python)) python = Path.Combine(folder, @".venv\Scripts\python.exe");
        if (!File.Exists(python)) python = Environment.GetEnvironmentVariable("FORM_PYTHON") ?? "";
        string dataFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FormStudio");
        string logPath = Path.Combine(dataFolder, "camera-startup.log");
        try
        {
            if (args.Length == 1 && args[0] == "--launcher-check")
            {
                if (!File.Exists(python) || !File.Exists(Path.Combine(folder, "live_camera.py")))
                    return 1;
                return 0;
            }
            if (!File.Exists(python))
                throw new FileNotFoundException("Extract the complete Windows release ZIP before opening FormStudio.exe. For a source checkout, run Setup.ps1 first.");
            if (!File.Exists(Path.Combine(folder, "live_camera.py")))
                throw new FileNotFoundException("Keep FormStudio.exe beside desktop_server.py and the runtime folder.");
            Directory.CreateDirectory(dataFolder);
            string electron = Path.Combine(folder, @"node_modules\electron\dist\electron.exe");
            var start = File.Exists(electron)
                ? new ProcessStartInfo(electron, "\"" + folder.TrimEnd('\\') + "\"")
                : new ProcessStartInfo(python, "\"" + Path.Combine(folder, "desktop_server.py") + "\" --browser");
            start.WorkingDirectory = folder;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardError = true;
            start.RedirectStandardOutput = true;
            start.EnvironmentVariables["PYTHONPATH"] = Path.Combine(folder, ".training-deps");
            start.EnvironmentVariables["MPLCONFIGDIR"] = Path.Combine(dataFolder, "matplotlib");
            start.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
            using (var log = new StreamWriter(logPath, false))
            using (var process = new Process())
            {
                process.StartInfo = start;
                object gate = new object();
                DataReceivedEventHandler record = (sender, e) => {
                    if (e.Data != null) lock (gate) { log.WriteLine(e.Data); log.Flush(); }
                };
                process.OutputDataReceived += record;
                process.ErrorDataReceived += record;
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                process.WaitForExit();
                if (process.ExitCode != 0)
                    throw new Exception("The camera app could not start or stopped unexpectedly.\n\nCheck that the camera is connected and isn't being used by another app.\n\nDetails: " + logPath);
            }
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "FORM | Unable to open camera", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 1;
        }
    }
}
