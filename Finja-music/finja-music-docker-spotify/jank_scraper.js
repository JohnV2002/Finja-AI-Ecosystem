// ======================================================================
//           Jank Mommy's BPM Scraper V3.2 - Spicetify Extension
// ======================================================================
//
//   Project: Finja - Twitch Interactivity Suite
//   Module: finja-music-docker-spotify
//   Author: J. Apps (JohnV2002 / Sodakiller1)
//   Version: 1.1.0
//   Description: Die absolute Brechstange! Spicetify extension that
//                scrapes BPM/Key from Spotify's DJ mode UI and POSTs
//                it to the local jank_controller.py server.
//                Uses 127.0.0.1 instead of localhost (IPv4 Fix).
//
// ----------------------------------------------------------------------
//
//   Copyright (c) 2026 J. Apps
//   Licensed under the MIT License.
//
// ======================================================================

(function JankScraper() {
    // Warten bis Spicetify geladen ist
    if (!Spicetify.Player) {
        setTimeout(JankScraper, 1000);
        return;
    }

    console.log("[*] Jank Mommy's Scraper V3.2 ist online! :3");
    if (Spicetify.showNotification) {
        Spicetify.showNotification("Scraper V3.2: IPv4 Fix aktiv! :3");
    }

    let letzterTrackId = "";

    // Wir gucken jetzt einfach alle 2 Sekunden stumpf nach, was gerade passiert
    setInterval(() => {
        try {
            const data = Spicetify.Player.data;
            // Wenn gerade gar nichts spielt oder geladen ist, abbrechen
            if (!data) return;

            // HA! Hier war der Fehler: Spicetify nennt das Lied in neueren Versionen "item" und nicht mehr "track"!
            const track = data.track || data.item;
            if (!track?.uri) return;

            const aktuellerTrackId = track.uri.split(":")[2];

            // Haben wir ein NEUES Lied entdeckt?
            if (aktuellerTrackId !== letzterTrackId) {
                letzterTrackId = aktuellerTrackId;
                console.log(`[*] Neues Lied erkannt: ${aktuellerTrackId}. Gebe UI 3 Sekunden zum Laden...`);

                // Wir warten 3 Sekunden, damit das UI die BPM rendern kann
                setTimeout(() => {
                    let bpmText = "0";
                    let keyText = "Unknown";

                    // Versuch 1: Deine genaue dj-info Struktur
                    let infoTop = document.querySelector('.dj-info-row-top');

                    if (infoTop) {
                        let spans = infoTop.querySelectorAll('span');
                        if (spans.length >= 2) {
                            keyText = spans[0].innerText.trim();
                            bpmText = spans[1].innerText.replaceAll(/bpm/gi, '').trim();
                        }
                    } else {
                        // Versuch 2: Notfall-Suche
                        let allTags = document.querySelectorAll('.dj-info-tag');
                        if (allTags.length > 0) {
                            keyText = allTags[0].innerText.trim();
                        }
                    }

                    console.log(`[+] ERBEUTET: BPM ${bpmText} | Key ${keyText}`);
                    if (Spicetify.showNotification) {
                        Spicetify.showNotification(`BPM: ${bpmText} | Key: ${keyText}`);
                    }

                    // Ab ans Mutterschiff! (Fix: 127.0.0.1 statt localhost wegen IPv6/IPv4 Routing Fehler!)
                    fetch("http://127.0.0.1:8080/submit", {
                        method: "POST",
                        body: JSON.stringify({
                            id: aktuellerTrackId,
                            bpm: bpmText,
                            key: keyText
                        })
                    }).catch(err => console.log("[-] Mutterschiff nicht da:", err));

                }, 3000); // 3 Sekunden warten nach Song-Wechsel
            }
        } catch (error) {
            console.log("[-] Fehler im Brechstangen-Loop:", error);
        }
    }, 2000); // Alle 2 Sekunden überprüfen
})();
