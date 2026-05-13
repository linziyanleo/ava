const { contextBridge, ipcRenderer } = require('electron');

const api = {
  selectDirectory: () => ipcRenderer.invoke('ava:selectDirectory'),
  openPath: (targetPath) => ipcRenderer.invoke('ava:openPath', targetPath),
  openLogs: () => ipcRenderer.invoke('ava:openLogs'),
  getAppConfig: () => ipcRenderer.invoke('ava:getAppConfig'),
  getCoreEndpoint: () => ipcRenderer.invoke('ava:getCoreEndpoint'),
  getAuthToken: () => ipcRenderer.invoke('ava:getAuthToken'),
  readDesktopConfig: () => ipcRenderer.invoke('ava:readDesktopConfig'),
  setNanobotRoot: (root) => ipcRenderer.invoke('ava:setNanobotRoot', root),
  retryCore: () => ipcRenderer.invoke('ava:retryCore'),
  cancelBootstrap: () => ipcRenderer.invoke('ava:cancelBootstrap'),
  showNotification: (payload) => ipcRenderer.invoke('ava:showNotification', payload),
  onBootstrapState: (callback) => {
    if (typeof callback !== 'function') return () => {};
    const listener = (_event, state) => callback(state);
    ipcRenderer.on('ava:bootstrapState', listener);
    return () => ipcRenderer.removeListener('ava:bootstrapState', listener);
  },
};

contextBridge.exposeInMainWorld('avaDesktop', api);
