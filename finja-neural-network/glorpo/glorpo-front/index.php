<?php
/**
 * Glorpo Front Router
 * ===================
 * Routes page requests and renders Glorpo-transpiled HTML.
 *
 * Main Responsibilities:
 * - Resolve the requested page from the p query parameter.
 * - Use the engine to convert page body markup.
 * - Emit the final HTML shell with Glorpo CSS and JS assets.
 *
 * Side Effects:
 * - Reads page files from disk.
 * - Sends HTTP status and content-type headers.
 * - Writes HTML directly to the response.
 */
require_once __DIR__ . '/glorpo-engine.php';

// Resolve the requested page.
$page = preg_replace('/[^a-zA-Z0-9\-_]/', '', $_GET['p'] ?? 'home');
$file = __DIR__ . '/pages/' . $page . '.html';

if (!file_exists($file)) {
    http_response_code(404);
    $file = __DIR__ . '/pages/404.html';
    if (!file_exists($file)) {
        // Fallback when no 404 page exists yet.
        header('Content-Type: text/html; charset=utf-8');
        echo '<glorphtml><glorpbod style="font-family:sans-serif;padding:2rem">';
        echo '<glorphat style="color:#a78bfa">404</glorphat>';
        echo '<glorp>Glorpo page not found: <glorpcode>' . htmlspecialchars($page) . '</glorpcode></glorp>';
        echo '<glorpwarp href="/"><- Back</glorpwarp>';
        echo '</glorpbod></glorphtml>';
        exit;
    }
}

// Process the page.
$result = glorpo_process_file($file);

// Emit the response.
header('Content-Type: text/html; charset=utf-8');
?><!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title><?= $result['title'] ?></title>
    <?= $result['head_extra'] ?>
    <link rel="stylesheet" href="glorpo.css">
</head>
<body>
<?= $result['body'] ?>
<script src="glorpo.js"></script>
</body>
</html>
