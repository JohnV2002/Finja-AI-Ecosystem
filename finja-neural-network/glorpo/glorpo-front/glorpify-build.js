#!/usr/bin/env node
/**
 * Glorpo Static Build Tool
 * ========================
 * Converts static HTML pages into Glorpo-tagged HTML.
 *
 * Main Responsibilities:
 * - Read source HTML files from an input directory.
 * - Translate body tags to Glorpo tags.
 * - Write converted output in-place or to a destination directory.
 *
 * Side Effects:
 * - Reads and writes HTML files on disk.
 * - Injects glorpo.css and glorpo.js references.
 * - Prints build status to stdout/stderr.
 */
const fs   = require('fs');
const path = require('path');

// Tag mapping.
const GLORPO_TAGS = {
    blockquote: 'glorpquote',
    figcaption: 'glorpcap',
    textarea:   'glorpwrite',
    section:    'glorpsect',
    article:    'glorpart',
    button:     'glorpclick',
    select:     'glorpchoose',
    figure:     'glorpfig',
    strong:     'glorpchonk',
    iframe:     'glorphole',
    footer:     'glorpfoot',
    header:     'glorphdr',
    option:     'glorpopt',
    label:      'glorplabel',
    aside:      'glorpaside',
    video:      'glorpvid',
    audio:      'glorpsound',
    table:      'glorptable',
    thead:      'glorpthead',
    tbody:      'glorptbod',
    input:      'glorpask',
    form:       'glorpform',
    main:       'glorpmain',
    span:       'glorpspan',
    code:       'glorpcode',
    pre:        'glorpraw',
    nav:        'glorpnav',
    div:        'glorpbox',
    img:        'glorppic',
    ul:         'glorpbag',
    ol:         'glorporder',
    li:         'glorpitem',
    tr:         'glorprow',
    td:         'glorpcell',
    th:         'glorpthcell',
    hr:         'glorpline',
    br:         'glorpsnap',
    em:         'glorpwiggly',
    h1:         'glorphat',
    h2:         'glorph2',
    h3:         'glorph3',
    h4:         'glorph4',
    h5:         'glorph5',
    h6:         'glorph6',
    a:          'glorpwarp',
    p:          'glorp',
};

const VOID_GLORPO_TAGS = new Set(['img', 'input', 'br', 'hr']);

// Glorpify all tags in one pass.
function glorpifyBody(html) {
    return html.replace(/<(\/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*?)(\/?)>/g,
        (match, close, tag, attrs, selfclose) => {
            const real = tag.toLowerCase();
            const glorpo = GLORPO_TAGS[real] ?? tag;
            if (!close && GLORPO_TAGS[real] && VOID_GLORPO_TAGS.has(real)) {
                return `<${glorpo}${attrs}></${glorpo}>`;
            }
            return `<${close}${glorpo}${attrs}${selfclose}>`;
        }
    );
}

// Extract head and body cleanly.
function processHtml(raw, cssPath) {
    // Title
    const titleMatch = raw.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    const title = titleMatch ? titleMatch[1] : 'Glorpo';

    // Head extras such as link, meta, style, and script tags, excluding title.
    const headMatch = raw.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
    let headExtra = '';
    if (headMatch) {
        headExtra = headMatch[1]
            .replace(/<title[^>]*>[\s\S]*?<\/title>/gi, '')
            .trim();
    }

    // Inject glorpo.css when it is not already present.
    const cssTag = `<link rel="stylesheet" href="${cssPath}">`;
    if (!headExtra.includes('glorpo.css')) {
        headExtra += '\n' + cssTag;
    }

    // Body
    const bodyMatch = raw.match(/<body([^>]*)>([\s\S]*?)<\/body>/i);
    const bodyAttrs = bodyMatch ? bodyMatch[1] : '';
    const bodyRaw   = bodyMatch ? bodyMatch[2] : raw;

    // Glorpify only the body.
    const bodyGlorpo = glorpifyBody(bodyRaw);

    // Inject glorpo.js before </body>.
    const jsPath = cssPath.replace('glorpo.css', 'glorpo.js');
    const jsTag  = `<script src="${jsPath}"></script>`;

    return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
${headExtra}
</head>
<body${bodyAttrs}>
${bodyGlorpo}
${jsTag}
</body>
</html>`;
}

// Find all HTML files recursively.
function findHtmlFiles(dir) {
    const results = [];
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            results.push(...findHtmlFiles(full));
        } else if (entry.isFile() && entry.name.endsWith('.html')) {
            results.push(full);
        }
    }
    return results;
}

// Calculate the relative path to glorpo.css.
function relPath(fromFile, toFile) {
    return path.relative(path.dirname(fromFile), toFile).replace(/\\/g, '/');
}

// Main.
const args    = process.argv.slice(2);
const dryRun  = args.includes('--dry');
const filtered = args.filter(a => !a.startsWith('--'));

const inputDir  = filtered[0];
const outputDir = filtered[1] || filtered[0]; // in-place when no output directory is provided.

if (!inputDir) {
    console.log(`
Glorpo Build Tool
Usage:
  node glorpify-build.js <input>          (in-place)
  node glorpify-build.js <input> <output> (write to dist folder)
  node glorpify-build.js <input> --dry    (preview only)

"Glorpo is pain."
`);
    process.exit(0);
}

if (!fs.existsSync(inputDir)) {
    console.error(`[!] Folder not found: ${inputDir}`);
    process.exit(1);
}

// Check whether glorpo.css exists in inputDir.
const cssSource = path.join(inputDir, 'glorpo.css');
const jsSource  = path.join(inputDir, 'glorpo.js');

if (!fs.existsSync(cssSource)) {
    console.warn(`[!] Warning: glorpo.css was not found in ${inputDir} - the CSS path may be wrong`);
}

// Create the output folder when needed.
const inPlace = path.resolve(inputDir) === path.resolve(outputDir);
if (!inPlace && !dryRun && !fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
}

const files = findHtmlFiles(inputDir);
console.log(`\nGlorpo Build Tool`);
console.log(`   Input : ${path.resolve(inputDir)}`);
console.log(`   Output: ${inPlace ? '(in-place)' : path.resolve(outputDir)}`);
console.log(`   Files : ${files.length} HTML files found`);
console.log(`   Mode  : ${dryRun ? 'DRY RUN (no files changed)' : 'LIVE'}\n`);

let ok = 0, skip = 0;

for (const file of files) {
    // Target path.
    const relative  = path.relative(path.resolve(inputDir), file);
    const outFile   = inPlace ? file : path.join(path.resolve(outputDir), relative);

    // glorpo.css path relative to the output file.
    const cssOut    = inPlace
        ? path.join(inputDir, 'glorpo.css')
        : path.join(outputDir, 'glorpo.css');
    const cssRel    = relPath(outFile, cssOut);

    try {
        const raw    = fs.readFileSync(file, 'utf8');
        const result = processHtml(raw, cssRel);

        if (dryRun) {
            console.log(`  [dry] ${relative}`);
        } else {
            if (!inPlace) {
                fs.mkdirSync(path.dirname(outFile), { recursive: true });
            }
            fs.writeFileSync(outFile, result, 'utf8');
            console.log(`  [OK]  ${relative}`);
        }
        ok++;
    } catch (e) {
        console.error(`  [!!] ${relative} - ${e.message}`);
        skip++;
    }
}

// Copy glorpo.css and glorpo.js into outputDir when output is separate.
if (!inPlace && !dryRun) {
    if (fs.existsSync(cssSource)) {
        fs.copyFileSync(cssSource, path.join(outputDir, 'glorpo.css'));
        console.log(`  [OK]  glorpo.css -> ${outputDir}`);
    }
    if (fs.existsSync(jsSource)) {
        fs.copyFileSync(jsSource,  path.join(outputDir, 'glorpo.js'));
        console.log(`  [OK]  glorpo.js  -> ${outputDir}`);
    }
}

console.log(`\n${dryRun ? 'Dry run complete' : 'Done'}: ${ok} files${skip ? `, ${skip} errors` : ''}`);
console.log(`"Glorpo is pain."\n`);
