<?php
/**
 * Glorpo Drop-In Front Engine
 * ===========================
 * Drop-in PHP engine for serving Glorpo-transpiled HTML files.
 *
 * Main Responsibilities:
 * - Serve existing HTML/HTM files as Glorpo markup.
 * - Convert body tags to Glorpo tags server-side.
 * - Provide debug-aware failure output.
 *
 * Side Effects:
 * - Reads requested files from disk.
 * - Sends HTTP status and content-type headers.
 * - Writes HTML directly to the response.
 */
set_time_limit(15);
ini_set('pcre.backtrack_limit', '1000000');

const GLORPO_TAGS = [
    'blockquote' => 'glorpquote',
    'figcaption' => 'glorpcap',
    'textarea'   => 'glorpwrite',
    'section'    => 'glorpsect',
    'article'    => 'glorpart',
    'button'     => 'glorpclick',
    'select'     => 'glorpchoose',
    'figure'     => 'glorpfig',
    'strong'     => 'glorpchonk',
    'iframe'     => 'glorphole',
    'footer'     => 'glorpfoot',
    'header'     => 'glorphdr',
    'option'     => 'glorpopt',
    'label'      => 'glorplabel',
    'aside'      => 'glorpaside',
    'video'      => 'glorpvid',
    'audio'      => 'glorpsound',
    'table'      => 'glorptable',
    'thead'      => 'glorpthead',
    'tbody'      => 'glorptbod',
    'input'      => 'glorpask',
    'form'       => 'glorpform',
    'main'       => 'glorpmain',
    'span'       => 'glorpspan',
    'code'       => 'glorpcode',
    'pre'        => 'glorpraw',
    'nav'        => 'glorpnav',
    'div'        => 'glorpbox',
    'img'        => 'glorppic',
    'ul'         => 'glorpbag',
    'ol'         => 'glorporder',
    'li'         => 'glorpitem',
    'tr'         => 'glorprow',
    'td'         => 'glorpcell',
    'th'         => 'glorpthcell',
    'hr'         => 'glorpline',
    'br'         => 'glorpsnap',
    'em'         => 'glorpwiggly',
    'h1'         => 'glorphat',
    'h2'         => 'glorph2',
    'h3'         => 'glorph3',
    'h4'         => 'glorph4',
    'h5'         => 'glorph5',
    'h6'         => 'glorph6',
    'a'          => 'glorpwarp',
    'p'          => 'glorp',
];

function glorpo_debug_enabled() {
    return isset($_COOKIE['glorpoDebug']) && $_COOKIE['glorpoDebug'] === '1';
}

function glorpo_fail($status, $message) {
    http_response_code($status);
    header('Content-Type: text/html; charset=utf-8');
    echo '<!DOCTYPE html><html><body style="font-family:sans-serif;padding:2rem">';
    echo '<h1>Glorpo</h1>';
    echo '<p>' . htmlspecialchars($message, ENT_QUOTES, 'UTF-8') . '</p>';
    echo '</body></html>';
    exit;
}

function glorpo_docroot() {
    $root = isset($_SERVER['DOCUMENT_ROOT']) ? $_SERVER['DOCUMENT_ROOT'] : __DIR__;
    $real = realpath($root);
    return $real !== false ? rtrim($real, '/\\') : rtrim($root, '/\\');
}

function glorpo_starts_with($value, $prefix) {
    return substr($value, 0, strlen($prefix)) === $prefix;
}

function glorpo_resolve($requested) {
    $requested = str_replace('\\', '/', (string)$requested);
    $requested = ltrim($requested, '/');

    if ($requested === '') return false;
    if (strpos($requested, '..') !== false) return false;
    if (!preg_match('/\.html?$/i', $requested)) return false;
    if (!preg_match('/^[a-zA-Z0-9\/_.\- ]+$/', $requested)) return false;

    $docroot = glorpo_docroot();
    $full = realpath($docroot . DIRECTORY_SEPARATOR . $requested);

    if ($full === false || !is_file($full)) return false;
    $full_norm = rtrim(str_replace('\\', '/', $full), '/');
    $root_norm = rtrim(str_replace('\\', '/', $docroot), '/');
    if (!glorpo_starts_with($full_norm, $root_norm . '/')) return false;

    return $full;
}

function glorpo_resolve_asset($requested, $extensions) {
    $requested = str_replace('\\', '/', (string)$requested);
    $requested = ltrim($requested, '/');

    if ($requested === '') return false;
    if (strpos($requested, '..') !== false) return false;
    if (!preg_match('/^[a-zA-Z0-9\/_.\- ]+$/', $requested)) return false;

    $ext = strtolower(pathinfo($requested, PATHINFO_EXTENSION));
    if (!isset($extensions[$ext])) return false;

    $docroot = glorpo_docroot();
    $full = realpath($docroot . DIRECTORY_SEPARATOR . $requested);

    if ($full === false || !is_file($full)) return false;
    $full_norm = rtrim(str_replace('\\', '/', $full), '/');
    $root_norm = rtrim(str_replace('\\', '/', $docroot), '/');
    if (!glorpo_starts_with($full_norm, $root_norm . '/')) return false;

    return $full;
}

function glorpo_page_relative_path($href, $page) {
    $href = trim(html_entity_decode($href, ENT_QUOTES, 'UTF-8'));
    if ($href === '') return false;
    if (preg_match('/^(?:https?:)?\/\//i', $href)) return false;
    if (preg_match('/^(?:data|blob|mailto|tel):/i', $href)) return false;

    $path = preg_replace('/[#?].*$/', '', $href);
    $path = str_replace('\\', '/', $path);

    if (glorpo_starts_with($path, '/')) {
        return ltrim($path, '/');
    }

    $page_dir = trim(dirname(str_replace('\\', '/', ltrim((string)$page, '/'))), '.');
    return ltrim(($page_dir !== '' ? $page_dir . '/' : '') . $path, '/');
}

function glorpo_css_url($css_path) {
    return 'glorpo.php?__glorpcss=' . rawurlencode($css_path);
}

function glorpo_rewrite_head_stylesheets($head, $page) {
    return preg_replace_callback(
        '/<link\b[^>]*>/i',
        function ($m) use ($page) {
            $tag = $m[0];
            if (!preg_match('/\brel\s*=\s*(["\']?)([^"\'>\s]*)\1/i', $tag, $rel)) return $tag;
            if (stripos($rel[2], 'stylesheet') === false) return $tag;
            if (!preg_match('/\bhref\s*=\s*(["\'])(.*?)\1/i', $tag, $href)) return $tag;

            $css_path = glorpo_page_relative_path($href[2], $page);
            if ($css_path === false || !preg_match('/\.css$/i', $css_path)) return $tag;

            $new_href = htmlspecialchars(glorpo_asset_prefix($page) . glorpo_css_url($css_path), ENT_QUOTES, 'UTF-8');
            return preg_replace('/\bhref\s*=\s*(["\'])(.*?)\1/i', 'href="' . $new_href . '"', $tag, 1);
        },
        $head
    );
}

function glorpo_rebase_css_urls($css, $css_path) {
    $dir = trim(dirname(str_replace('\\', '/', ltrim((string)$css_path, '/'))), '.');

    return preg_replace_callback(
        '/url\(\s*([\'"]?)(.*?)\1\s*\)/i',
        function ($m) use ($dir) {
            $url = trim($m[2]);
            if ($url === '' || preg_match('/^(?:https?:)?\/\//i', $url)) return $m[0];
            if (preg_match('/^(?:data|blob):/i', $url)) return $m[0];
            if (glorpo_starts_with($url, '/')) return 'url("' . $url . '")';

            $rebased = '/' . ltrim(($dir !== '' ? $dir . '/' : '') . $url, '/');
            return 'url("' . str_replace('"', '%22', $rebased) . '")';
        },
        $css
    );
}

function glorpo_css_selector_map($selector) {
    static $map = null;
    if ($map === null) {
        $map = GLORPO_TAGS;
        $map['body'] = 'body';
        $map['html'] = 'html';
    }

    $mapped = preg_replace_callback(
        '/(^|[\s>+~,(])([a-zA-Z][a-zA-Z0-9_-]*)(?=[:.#\[\s>+~,\)]|$)/',
        function ($m) use ($map) {
            $tag = strtolower($m[2]);
            if (!isset($map[$tag]) || $map[$tag] === $tag) return $m[0];
            return $m[1] . $map[$tag];
        },
        $selector
    );

    return $mapped !== $selector ? $mapped : '';
}

function glorpo_mirror_css_selectors($css) {
    return preg_replace_callback(
        '/(^|[{}])([^{}@][^{}]*)\{/m',
        function ($m) {
            $prefix = $m[1];
            $selector = trim($m[2]);
            if ($selector === '' || preg_match('/^(?:from|to|\d+%)/i', $selector)) {
                return $m[0];
            }

            $parts = explode(',', $selector);
            $mirrors = [];
            foreach ($parts as $part) {
                $mirror = glorpo_css_selector_map(trim($part));
                if ($mirror !== '') $mirrors[] = $mirror;
            }

            if (!$mirrors) return $m[0];
            return $prefix . $selector . ', ' . implode(', ', array_unique($mirrors)) . ' {';
        },
        $css
    );
}

function glorpo_serve_css($requested) {
    $path = urldecode((string)$requested);
    $filepath = glorpo_resolve_asset($path, ['css' => true]);
    if ($filepath === false) {
        glorpo_fail(404, 'Glorpo CSS file not found: ' . $path);
    }

    $css = file_get_contents($filepath);
    if ($css === false) {
        glorpo_fail(500, 'Could not read Glorpo CSS file.');
    }

    $css = glorpo_rebase_css_urls($css, $path);
    $css = glorpo_mirror_css_selectors($css);

    header('Content-Type: text/css; charset=utf-8');
    echo $css;
    exit;
}

function glorpify($html) {
    $void_glorpo_tags = [
        'img'   => true,
        'input' => true,
        'br'    => true,
        'hr'    => true,
    ];

    return preg_replace_callback(
        '/<(\/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*?)(\/?)\s*>/s',
        function ($m) use ($void_glorpo_tags) {
            $close = $m[1];
            $tag = strtolower($m[2]);
            $attrs = $m[3];
            $selfclose = $m[4];
            $glorpo = isset(GLORPO_TAGS[$tag]) ? GLORPO_TAGS[$tag] : $tag;

            // HTML void tags like <img> and <br> become custom Glorpo tags.
            // Custom tags are not void in text/html, so they must be closed
            // explicitly or the browser nests the rest of the page inside them.
            if ($close === '' && isset($void_glorpo_tags[$tag]) && isset(GLORPO_TAGS[$tag])) {
                return '<' . $glorpo . $attrs . '></' . $glorpo . '>';
            }

            return '<' . $close . $glorpo . $attrs . $selfclose . '>';
        },
        $html
    );
}

function glorpo_extract($raw) {
    $head_extra = '';
    $title = 'Glorpo';

    $t_open = stripos($raw, '<title');
    if ($t_open !== false) {
        $t_start = strpos($raw, '>', $t_open);
        if ($t_start !== false) {
            $t_end = stripos($raw, '</title>', $t_start);
            if ($t_end !== false) {
                $title = htmlspecialchars(strip_tags(substr($raw, $t_start + 1, $t_end - $t_start - 1)), ENT_QUOTES, 'UTF-8');
            }
        }
    }

    $head_open = stripos($raw, '<head');
    $head_close = stripos($raw, '</head>');
    if ($head_open !== false && $head_close !== false) {
        $head_start = strpos($raw, '>', $head_open);
        if ($head_start !== false) {
            $head_inner = substr($raw, $head_start + 1, $head_close - $head_start - 1);
            $head_extra = preg_replace('/<title[^>]*>.*?<\/title>/is', '', $head_inner);
            $head_extra = strip_tags($head_extra, '<link><meta><style><script>');
        }
    }

    $body_attrs = '';
    $body_raw = $raw;
    $body_open = stripos($raw, '<body');
    if ($body_open !== false) {
        $body_tag_end = strpos($raw, '>', $body_open);
        if ($body_tag_end !== false) {
            $body_attrs = trim(substr($raw, $body_open + 5, $body_tag_end - $body_open - 5));
            $body_start = $body_tag_end + 1;
            $body_close = strripos($raw, '</body>');
            $body_raw = $body_close !== false
                ? substr($raw, $body_start, $body_close - $body_start)
                : substr($raw, $body_start);
        }
    }

    return [$title, $head_extra, $body_attrs, $body_raw];
}

function glorpo_asset_prefix($requested) {
    $requested = str_replace('\\', '/', ltrim($requested, '/'));
    $depth = substr_count($requested, '/');
    return $depth > 0 ? str_repeat('../', $depth) : '';
}

if (glorpo_debug_enabled()) {
    error_reporting(E_ALL);
    ini_set('display_errors', '1');
}

if (isset($_GET['__glorpcss'])) {
    glorpo_serve_css($_GET['__glorpcss']);
}

if (!isset($_GET['f'])) {
    glorpo_fail(403, 'Glorpo is pain. This file is meant to be called by .htaccess.');
}

$requested = $_GET['f'];
$filepath = glorpo_resolve($requested);
if ($filepath === false) {
    glorpo_fail(404, 'Glorpo file not found: ' . $requested);
}

$raw = file_get_contents($filepath);
if ($raw === false) {
    glorpo_fail(500, 'Could not read Glorpo source file.');
}

list($title, $head_extra, $body_attrs, $body_raw) = glorpo_extract($raw);
$head_extra = glorpo_rewrite_head_stylesheets($head_extra, $requested);
if (glorpo_debug_enabled() && isset($_GET['__glorpnoscripts'])) {
    $head_extra = preg_replace('/<script\b[^>]*>.*?<\/script>/is', '', $head_extra);
    $head_extra = preg_replace('/<script\b[^>]*\/?>/is', '', $head_extra);
    $body_raw = preg_replace('/<script\b[^>]*>.*?<\/script>/is', '', $body_raw);
    $body_raw = preg_replace('/<script\b[^>]*\/?>/is', '', $body_raw);
}
$body_glorpo = glorpify($body_raw);
$pre = glorpo_asset_prefix($requested);

header('Content-Type: text/html; charset=utf-8');
?><!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= $title ?></title>
<link rel="stylesheet" href="<?= htmlspecialchars($pre . 'glorpo.css', ENT_QUOTES, 'UTF-8') ?>">
<script src="<?= htmlspecialchars($pre . 'glorpo.js', ENT_QUOTES, 'UTF-8') ?>"></script>
<?= $head_extra ?>
</head>
<body<?= $body_attrs ? ' ' . $body_attrs : '' ?>>
<?php if (glorpo_debug_enabled()): ?>
<script>
console.log('[GlorpoFront PHP] debug page delivered', {
  file: <?= json_encode((string)$requested) ?>,
  noScripts: <?= isset($_GET['__glorpnoscripts']) ? 'true' : 'false' ?>,
  bodyLength: <?= (int)strlen($body_glorpo) ?>
});
</script>
<?php endif; ?>
<?= $body_glorpo ?>
</body>
</html>
