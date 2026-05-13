import net from 'node:net';

export function listenOnPort(port, host = '127.0.0.1') {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(port, host, () => {
      const address = server.address();
      const selected = typeof address === 'object' && address ? address.port : port;
      server.close(() => resolve(selected));
    });
  });
}

export async function pickFreePort(preferred, host = '127.0.0.1') {
  try {
    return await listenOnPort(preferred, host);
  } catch (error) {
    if (error?.code !== 'EADDRINUSE' && error?.code !== 'EACCES') {
      throw error;
    }
    return listenOnPort(0, host);
  }
}
