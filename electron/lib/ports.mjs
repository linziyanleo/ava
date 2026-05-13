import net from 'node:net';

export function listenOnPort(port) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => {
      const address = server.address();
      const selected = typeof address === 'object' && address ? address.port : port;
      server.close(() => resolve(selected));
    });
  });
}

export async function pickFreePort(preferred) {
  try {
    return await listenOnPort(preferred);
  } catch (error) {
    if (error?.code !== 'EADDRINUSE' && error?.code !== 'EACCES') {
      throw error;
    }
    return listenOnPort(0);
  }
}
