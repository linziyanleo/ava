import https from 'node:https';

export const DEFAULT_UPDATE_REPO = 'linziyanleo/ava';

function assertRepoSlug(repo) {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo)) {
    throw new Error(`invalid GitHub repo slug: ${repo}`);
  }
}

function normalizeVersion(version) {
  const raw = String(version || '').trim().replace(/^v/i, '');
  const core = raw.split(/[+-]/, 1)[0];
  const parts = core.split('.').map((part) => Number(part));
  if (parts.length !== 3 || parts.some((part) => !Number.isInteger(part) || part < 0)) {
    throw new Error(`invalid semver version: ${version}`);
  }
  return parts;
}

export function compareVersions(left, right) {
  const leftParts = normalizeVersion(left);
  const rightParts = normalizeVersion(right);
  for (let index = 0; index < 3; index += 1) {
    if (leftParts[index] > rightParts[index]) return 1;
    if (leftParts[index] < rightParts[index]) return -1;
  }
  return 0;
}

export function latestReleaseUrl(repo = process.env.AVA_UPDATE_REPO || DEFAULT_UPDATE_REPO) {
  assertRepoSlug(repo);
  return `https://api.github.com/repos/${repo}/releases/latest`;
}

export function githubRequestHeaders({ token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN } = {}) {
  const headers = {
    Accept: 'application/vnd.github+json',
    'User-Agent': 'ava-desktop-update-check',
  };
  const trimmedToken = String(token || '').trim();
  if (trimmedToken) {
    headers.Authorization = `Bearer ${trimmedToken}`;
  }
  return headers;
}

export function fetchJson(url) {
  return new Promise((resolve, reject) => {
    const request = https.get(
      url,
      {
        headers: githubRequestHeaders(),
      },
      (response) => {
        let body = '';
        response.setEncoding('utf8');
        response.on('data', (chunk) => {
          body += chunk;
        });
        response.on('end', () => {
          if (response.statusCode !== 200) {
            reject(new Error(`GitHub latest release request failed with status ${response.statusCode}`));
            return;
          }
          try {
            resolve(JSON.parse(body));
          } catch (error) {
            reject(error);
          }
        });
      },
    );
    request.on('error', reject);
    request.setTimeout(10_000, () => {
      request.destroy(new Error('GitHub latest release request timed out'));
    });
  });
}

export async function checkForUpdate({
  currentVersion,
  repo = process.env.AVA_UPDATE_REPO || DEFAULT_UPDATE_REPO,
  requestJson = fetchJson,
} = {}) {
  if (!currentVersion) {
    throw new Error('currentVersion is required');
  }
  const release = await requestJson(latestReleaseUrl(repo));
  const latestVersion = release?.tag_name;
  const releaseUrl = release?.html_url;
  if (typeof latestVersion !== 'string' || typeof releaseUrl !== 'string') {
    throw new Error('GitHub latest release payload is missing tag_name or html_url');
  }
  return {
    available: compareVersions(latestVersion, currentVersion) > 0,
    version: latestVersion,
    url: releaseUrl,
  };
}
