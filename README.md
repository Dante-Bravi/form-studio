# FORM Studio

Webcam exercise sessions with curl counting and a three-line PDF summary.

## Run on Windows

1. Download **FormStudio-Windows-x64.zip** from this repository's **Releases**.
2. Extract the entire ZIP, then double-click **FormStudio.exe**.
3. Choose an exercise and rep goal, then start. Download the PDF when finished.

Windows 10/11 x64, a webcam, and Microsoft Edge are required. The release includes Python, dependencies, and model weights; no Python or Node.js installation is needed. Keep the extracted files together.

Curls count automatically **per arm**. Other exercises use **Log completed rep**. Pauses are excluded from elapsed time. Camera processing stays on your computer.

## Run from source

Install Python 3.12 x64, open PowerShell here, and run `./Setup.ps1`. Then open `FormStudio.exe`. For the optional Electron frontend, install Node.js and run `npm install` followed by `npm start`.

Model recognition is experimental; the video-window validation scores are not live repetition-count accuracy. Third-party model/data attribution is in [THIRD_PARTY.md](THIRD_PARTY.md).
