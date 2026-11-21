const {app, BrowserWindow, dialog} = require('electron');
const {spawn} = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
let backend;
app.whenReady().then(() => {
  const root = path.resolve(__dirname, '..');
  const python = [path.join(root,'runtime/python.exe'),path.join(root,'.venv/Scripts/python.exe'),process.env.FORM_PYTHON].find(file=>file&&fs.existsSync(file));
  if(!python){dialog.showErrorBox('Python runtime missing','Extract the complete release ZIP, or run Setup.ps1 for a source checkout.');app.quit();return;}
  const dataFolder=app.getPath('userData');
  fs.mkdirSync(dataFolder,{recursive:true});
  backend = spawn(python, [path.join(root, 'desktop_server.py')], {
    cwd: root, windowsHide: true,
    env: {...process.env, PYTHONUNBUFFERED:'1', PYTHONPATH: path.join(root,'.training-deps'), MPLCONFIGDIR: path.join(dataFolder,'matplotlib')}
  });
  const log = fs.createWriteStream(path.join(dataFolder, 'camera-startup.log'));
  backend.stderr.pipe(log);
  let opened = false, output = '';
  backend.stdout.on('data', chunk => {
    output += chunk.toString();
    const match = output.match(/FORM_URL=(http:\/\/127\.0\.0\.1:\d+)/);
    if (!opened && match) {
      opened = true;
      const win = new BrowserWindow({width:1440,height:960,minWidth:1000,minHeight:740,
        backgroundColor:'#f5f5f0',title:'FORM Studio',icon:path.join(root,'FORM.ico'),
        autoHideMenuBar:true,webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true}});
      win.webContents.setWindowOpenHandler(() => ({action:'deny'}));
      win.webContents.on('will-navigate', (event,url) => { if (!url.startsWith(match[1]+'/')) event.preventDefault(); });
      win.loadURL(match[1]);
    }
  });
  backend.on('error', error => {dialog.showErrorBox('Unable to start FORM',error.message);app.quit();});
  backend.on('exit', code => {if (code && !app.isQuitting) dialog.showErrorBox('FORM stopped','See camera-startup.log for details.');app.quit();});
});
app.on('before-quit',()=>{app.isQuitting=true;if(backend)backend.kill();});
app.on('window-all-closed',()=>app.quit());
