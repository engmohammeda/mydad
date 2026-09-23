import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;
const HOST = '0.0.0.0';

// Serve static assets from docs directory
app.use(express.static(path.join(__dirname, 'docs')));

// Also serve haraj-riyadh-2026 directory if referenced
app.use('/haraj-riyadh-2026', express.static(path.join(__dirname, 'haraj-riyadh-2026')));

// Catch-all: serve index.html
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'docs', 'index.html'));
});

app.listen(PORT, HOST, () => {
  console.log(`Server listening on http://${HOST}:${PORT}`);
});
