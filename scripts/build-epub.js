#!/usr/bin/env node
/**
 * Build EPUB from docs/ markdown files using Pandoc.
 * Outputs: epub/git-going-with-github.epub
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const DOCS = path.join(ROOT, 'docs');
const OUT = path.join(ROOT, 'epub', 'git-going-with-github.epub');
const METADATA = path.join(ROOT, 'epub', 'metadata.yaml');
const CSS = path.join(ROOT, 'epub', 'epub.css');

// Ordered file list: course-guide first, then 00-16, then appendices a-z
function getDocFiles() {
  const all = fs.readdirSync(DOCS)
    .filter(f => f.endsWith('.md'))
    .sort();

  const courseGuide = all.filter(f => f === 'course-guide.md');
  const chapters = all.filter(f => /^\d{2}-/.test(f));
  const appendices = all.filter(f => f.startsWith('appendix-'));
  const rest = all.filter(f =>
    !courseGuide.includes(f) &&
    !chapters.includes(f) &&
    !appendices.includes(f)
  );

  return [...courseGuide, ...chapters, ...appendices, ...rest]
    .map(f => path.join(DOCS, f));
}

const files = getDocFiles();

console.log(`Building EPUB from ${files.length} files...\n`);
files.forEach(f => console.log(' ', path.relative(ROOT, f)));

const fileArgs = files.map(f => `"${f}"`).join(' ');

const cmd = [
  'pandoc',
  '--from markdown+smart',
  '--to epub3',
  `--output "${OUT}"`,
  `--metadata-file "${METADATA}"`,
  `--css "${CSS}"`,
  '--toc',
  '--toc-depth=2',
  '--split-level=1',
  '--syntax-highlighting=tango',
  '--wrap=none',
  fileArgs
].join(' \\\n  ');

console.log('\nRunning pandoc...\n');

try {
  execSync(cmd, { stdio: 'inherit', cwd: ROOT });
  const size = (fs.statSync(OUT).size / 1024).toFixed(1);
  console.log(`\nDone. EPUB written to: epub/git-going-with-github.epub (${size} KB)`);
} catch (err) {
  console.error('\nPandoc failed. Is pandoc installed? Run: brew install pandoc');
  process.exit(1);
}
