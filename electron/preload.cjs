const { contextBridge, ipcRenderer } = require('electron');

const api = {
  selectDirectory: () => ipcRenderer.invoke('ava:selectDirectory'),
  openPath: (targetPath) => ipcRenderer.invoke('ava:openPath', targetPath),
  getAppConfig: () => ipcRenderer.invoke('ava:getAppConfig'),
  getCoreEndpoint: () => ipcRenderer.invoke('ava:getCoreEndpoint'),
  getAuthToken: () => ipcRenderer.invoke('ava:getAuthToken'),
  showNotification: (payload) => ipcRenderer.invoke('ava:showNotification', payload),
};

contextBridge.exposeInMainWorld('avaDesktop', api);
