<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Any Downloader</title>
  <style>
    body { font-family: sans-serif; padding: 2rem; background-color: #f7f7f7; }
    .container { max-width: 600px; margin: 0 auto; background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
    .status { margin-top: 1rem; padding: 0.5rem; border-radius: 4px; display: none; }
    .status.success { background: #e9fce9; border: 1px solid #5cb85c; color: #3c763d; }
    .status.error { background: #fdeaea; border: 1px solid #d9534f; color: #a94442; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Any Downloader</h1>
    <label for="url">Video URL:</label>
    <input type="url" id="url" placeholder="Enter video URL" style="width:100%; padding:8px; margin-top:4px;" />
    <label for="format" style="margin-top:12px;">Format:</label>
    <select id="format" style="width:100%; padding:8px;">
      <option value="best">Auto (best)</option>
      <option value="bestaudio">Audio only</option>
      <option value="best[ext=mp4]">MP4 only</option>
    </select>
    <button id="downloadBtn" style="margin-top:12px; padding:10px; width:100%;">Download</button>
    <div id="status" class="status"></div>
  </div>
  <script>
    document.getElementById('downloadBtn').addEventListener('click', async function () {
      const url = document.getElementById('url').value.trim();
      const format = document.getElementById('format').value;
      const statusEl = document.getElementById('status');
      statusEl.style.display = 'none';

      if (!url) {
        statusEl.textContent = "Please enter a video URL.";
        statusEl.className = 'status error';
        statusEl.style.display = 'block';
        return;
      }

      statusEl.textContent = "Processing...";
      statusEl.className = 'status';
      statusEl.style.display = 'block';

      try {
        const res = await fetch('/api/download-and-upload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url, format: format })
        });
        const data = await res.json();

        if (!res.ok) throw new Error(data.detail || 'Download failed');
        statusEl.className = 'status success';
        statusEl.textContent = `Download complete: ${data.filename}`;
      } catch (err) {
        statusEl.className = 'status error';
        statusEl.textContent = `Error: ${err.message}`;
      }
    });
  </script>
</body>
</html>
