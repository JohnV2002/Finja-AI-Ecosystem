<?php
/**
 * Glorpo HTML Transpiler Engine
 * =============================
 * Converts regular HTML body markup into Glorpo custom tags.
 *
 * Main Responsibilities:
 * - Map standard HTML tags to Glorpo tag names.
 * - Read page files and extract title, head extras, and body content.
 * - Return processed page fragments to the front router.
 *
 * Side Effects:
 * - Reads HTML files from disk.
 * - Sanitizes and returns head metadata for rendering.
 */
const GLORPO_TAG_MAP = [
    // Longer tags first to avoid partial matches, for example blockquote before b.
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

/**
 * Converts all HTML tags in the given HTML string into Glorpo tags.
 * Processes only body content so the head remains functional.
 */
function glorpify_html(string $html): string {
    $void_tags = ['img' => true, 'input' => true, 'br' => true, 'hr' => true];

    return preg_replace_callback(
        '/<(\/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*?)(\/?)\s*>/s',
        function (array $m) use ($void_tags): string {
            $close = $m[1];
            $tag = strtolower($m[2]);
            $attrs = $m[3];
            $selfclose = $m[4];
            $glorpo = GLORPO_TAG_MAP[$tag] ?? $tag;

            if ($close === '' && isset($void_tags[$tag]) && isset(GLORPO_TAG_MAP[$tag])) {
                return '<' . $glorpo . $attrs . '></' . $glorpo . '>';
            }

            return '<' . $close . $glorpo . $attrs . $selfclose . '>';
        },
        $html
    );
}

/**
 * Reads an HTML file, extracts head and body data, and glorpifies the body.
 * Returns ['title' => ..., 'head_extra' => ..., 'body' => ...].
 */
function glorpo_process_file(string $filepath): array {
    $raw = file_get_contents($filepath);

    // Extract the title.
    preg_match('/<title[^>]*>(.*?)<\/title>/is', $raw, $title_m);
    $title = $title_m[1] ?? 'Glorpo Web';

    // Extract head extras such as link, meta, style, and script tags, excluding title.
    preg_match('/<head[^>]*>(.*?)<\/head>/is', $raw, $head_m);
    $head_raw = $head_m[1] ?? '';
    // Remove title because the wrapper sets it explicitly.
    $head_extra = preg_replace('/<title[^>]*>.*?<\/title>/is', '', $head_raw);
    // Allow only safe head tags.
    $head_extra = strip_tags($head_extra, '<link><meta><style><script>');

    // Extract body content.
    preg_match('/<body[^>]*>(.*?)<\/body>/is', $raw, $body_m);
    $body_raw = $body_m[1] ?? $raw;

    // Glorpify the body.
    $body_glorpo = glorpify_html($body_raw);

    return [
        'title'      => htmlspecialchars(strip_tags($title)),
        'head_extra' => $head_extra,
        'body'       => $body_glorpo,
    ];
}
