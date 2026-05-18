const { contextBridge, ipcRenderer } = require('electron');

const api = {
  platform: process.platform,
  selectDirectory: () => ipcRenderer.invoke('ava:selectDirectory'),
  revealArtifact: (artifactId) => ipcRenderer.invoke('ava:revealArtifact', artifactId),
  openLogs: () => ipcRenderer.invoke('ava:openLogs'),
  getAppConfig: () => ipcRenderer.invoke('ava:getAppConfig'),
  getCoreEndpoint: () => ipcRenderer.invoke('ava:getCoreEndpoint'),
  getAuthToken: () => ipcRenderer.invoke('ava:getAuthToken'),
  getBootstrapState: () => ipcRenderer.invoke('ava:getBootstrapState'),
  rendererReady: () => ipcRenderer.invoke('ava:rendererReady'),
  readDesktopConfig: () => ipcRenderer.invoke('ava:readDesktopConfig'),
  setNanobotRoot: (root) => ipcRenderer.invoke('ava:setNanobotRoot', root),
  setBadgeCount: (count) => ipcRenderer.invoke('ava:setBadgeCount', count),
  retryCore: () => ipcRenderer.invoke('ava:retryCore'),
  cancelBootstrap: () => ipcRenderer.invoke('ava:cancelBootstrap'),
  showNotification: (payload) => ipcRenderer.invoke('ava:showNotification', payload),
  onBootstrapState: (callback) => {
    if (typeof callback !== 'function') return () => {};
    const listener = (_event, state) => callback(state);
    ipcRenderer.on('ava:bootstrapState', listener);
    return () => ipcRenderer.removeListener('ava:bootstrapState', listener);
  },
  onOpenTaskFloater: (callback) => {
    if (typeof callback !== 'function') return () => {};
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on('ava:openTaskFloater', listener);
    return () => ipcRenderer.removeListener('ava:openTaskFloater', listener);
  },
  onDeepLink: (callback) => {
    if (typeof callback !== 'function') return () => {};
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on('ava:deepLink', listener);
    return () => ipcRenderer.removeListener('ava:deepLink', listener);
  },
};

contextBridge.exposeInMainWorld('avaDesktop', api);
