const releases = 'https://github.com/minichao9901/zynqlinkPRO/releases';
const latest = 'https://api.github.com/repos/minichao9901/zynqlinkPRO/releases/latest';
const asset = 'zynq-etm-bridge-win64.zip';
let requestPending = false;

export async function showDownloadRelease(){
  const version = document.getElementById('download-version');
  const download = document.getElementById('download-exe');
  const details = document.getElementById('download-release');
  if (!version || !download || !details || requestPending) return;
  requestPending = true;
  version.textContent = '最新发布';
  download.href = `${releases}/latest/download/${asset}`;
  details.href = `${releases}/latest`;

  try {
    const response = await fetch(latest, {signal:AbortSignal.timeout(6000)});
    if (!response.ok) return;
    const release = await response.json();
    const tag = release.tag_name;
    if (release.draft || release.prerelease || typeof tag !== 'string' || !/^v\d+\.\d+\.\d+$/.test(tag) ||
        !release.assets?.some(entry => entry.name === asset && entry.state === 'uploaded')) return;
    download.href = `${releases}/download/${tag}/${asset}`;
    details.href = `${releases}/tag/${tag}`;
    version.textContent = tag;
  } catch {
    // The latest-release links remain usable if the API is unavailable.
  } finally {
    requestPending = false;
  }
}
