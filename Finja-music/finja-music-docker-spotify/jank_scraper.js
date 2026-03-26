// ======================================================================
//           Jank Mommy's BPM Scraper V3.2 - Spicetify Extension
// ======================================================================
//
//   Project: Finja - Twitch Interactivity Suite
//   Module: finja-music-docker-spotify
//   Author: J. Apps (JohnV2002 / Sodakiller1)
//   Version: 1.1.0
//   Description: The absolute sledgehammer! Spicetify extension that
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
    // Wait until Spicetify is loaded
    if (!Spicetify.Player) {
        setTimeout(JankScraper, 1000);
        return;
    }

    console.log("[*] Jank Mommy's Scraper V3.2 is online! :3");
    if (Spicetify.showNotification) {
        Spicetify.showNotification("Scraper V3.2: IPv4 Fix active! :3");
    }

    let lastTrackId = "";

    // We check every 2 seconds what's currently happening
    setInterval(() => {
        try {
            const data = Spicetify.Player.data;
            // If nothing is playing or loaded, return
            if (!data) return;

            // Spicetify renamed the track to "item" in newer versions!
            const track = data.track || data.item;
            if (!track?.uri) return;

            const currentTrackId = track.uri.split(":")[2];

            // Did we discover a NEW song?
            if (currentTrackId !== lastTrackId) {
                lastTrackId = currentTrackId;
                console.log(`[*] New song detected: ${currentTrackId}. Giving UI 3 seconds to load...`);

                // We wait 3 seconds so the UI can render the BPM
                setTimeout(() => {
                    let bpmText = "0";
                    let keyText = "Unknown";

                    // Attempt 1: Exact dj-info structure
                    let infoTop = document.querySelector('.dj-info-row-top');

                    if (infoTop) {
                        let spans = infoTop.querySelectorAll('span');
                        if (spans.length >= 2) {
                            keyText = spans[0].innerText.trim();
                            bpmText = spans[1].innerText.replaceAll(/bpm/gi, '').trim();
                        }
                    } else {
                        // Attempt 2: Emergency search
                        let allTags = document.querySelectorAll('.dj-info-tag');
                        if (allTags.length > 0) {
                            keyText = allTags[0].innerText.trim();
                        }
                    }

                    console.log(`[+] CAPTURED: BPM ${bpmText} | Key ${keyText}`);
                    if (Spicetify.showNotification) {
                        Spicetify.showNotification(`BPM: ${bpmText} | Key: ${keyText}`);
                    }

                    // Send to Mothership! (Fix: 127.0.0.1 instead of localhost due to IPv6/IPv4 routing issues!)
                    fetch("http://127.0.0.1:8080/submit", {
                        method: "POST",
                        body: JSON.stringify({
                            id: currentTrackId,
                            bpm: bpmText,
                            key: keyText
                        })
                    }).catch(err => console.log("[-] Mothership unreachable:", err));

                }, 3000); // Wait 3 seconds after song change
            }
        } catch (error) {
            console.log("[-] Error in sledgehammer loop:", error);
        }
    }, 2000); // Check every 2 seconds
})();
