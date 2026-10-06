'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('syncApi', Object.freeze({
  getState: () => ipcRenderer.invoke('sync:state'),
  sync: () => ipcRenderer.invoke('sync:start'),
  setLanguage: language => ipcRenderer.invoke('sync:language', language),
  openClaude: () => ipcRenderer.invoke('sync:open'),
  showFiles: () => ipcRenderer.invoke('sync:files'),
  showBackup: () => ipcRenderer.invoke('sync:backup'),
  chooseClaude: () => ipcRenderer.invoke('sync:choose-claude'),
  chooseDataDirectory: () => ipcRenderer.invoke('sync:choose-data'),
  chooseProjectsDirectory: () => ipcRenderer.invoke('sync:choose-projects'),
  onState: callback => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on('sync:changed', listener);
    return () => ipcRenderer.removeListener('sync:changed', listener);
  },
}));
