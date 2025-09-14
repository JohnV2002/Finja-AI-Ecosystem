# 🐾 Finja – VPet Simulator Mods

Ein zentrales Repository für alle interaktiven Erweiterungen des VPet-Simulators für **Finja**.  
Dieses Projekt hat das Ziel, Finja lebendiger und interaktiver für Stream-Zuschauer zu machen, indem sie auf Musik, Chat-Befehle und mehr reagieren kann. 💖

---

## 📢 Wichtiger Hinweis: Alles ist in Arbeit!

🚧 **WORK IN PROGRESS** 🚧

Dieses gesamte Projekt befindet sich in einer **frühen Konzeptions- und Planungsphase**.  
Die hier beschriebenen Module sind **noch nicht implementiert**. Der Code wird erst noch geschrieben.  
Schau regelmäßig vorbei, um den Fortschritt zu sehen! :3

---

## ✨ Projekt-Philosophie

Die Idee ist, Finja von einem passiven VPet zu einer aktiven Stream-Partnerin zu entwickeln. Zuschauer sollen direkte, sichtbare Interaktionen mit ihr durchführen können, was die Bindung und den Unterhaltungswert erhöht. Alle Module sind so konzipiert, dass sie modular und erweiterbar sind.

---

## 📦 Die Module im Detail

Hier ist eine ausführliche Übersicht über jedes geplante Modul, das in den Unterordnern dieses Projekts entwickelt wird.

### 💃 Modul 1: Dance to Music
Dieses Modul erweckt Finja zur Tänzerin! Anstatt nur still dazusitzen, wird sie auf Musik reagieren, die ihr "gefällt".

-   **Status:** 💡 Konzeptphase
-   **Kern-Idee:** Wenn über ein externes "Musik-Gehirn" ein Lied als "Liked" markiert wird, löst dieses Modul eine passende Tanzanimation bei Finja aus.
-   **Geplante Features:**
    -   **Automatische Reaktion:** Lauscht auf "Liked"-Events von einem Musikerkennungs-Tool.
    -   **Genre-basierte Animationen:** Finja tanzt nicht immer gleich! Je nach Genre des Liedes (z.B. Pop, Rock, Lofi) wird eine andere, passende Animation ausgewählt.
    -   **Visuelles Feedback:** Eine kleine Note oder ein Herz könnte kurz aufploppen, um zu signalisieren, dass sie den Song mag und deshalb tanzt.
    -   **Optionale Chat-Logs:** Kann im Chat posten, z.B. _"Finja gefällt dieser Song und sie tanzt!"_

### 💬 Modul 2: Chat-Commands (Visuelle Ebene)
Dieses Modul ist die **visuelle Erweiterung** für den Chatbot. Es sorgt dafür, dass Finja auf Befehle nicht nur im Text-Chat, sondern auch **visuell mit Animationen** reagiert.

-   **Status:** 💡 Konzeptphase (Anbindung an existierendes `finja-chat` Projekt)
-   **Kern-Idee:** Dieses Modul stellt die Brücke zum bereits fertigen `finja-chat` Twitch-Modul her. `finja-chat` hört auf den Chat (via **ComfyJS**) und erkennt Befehle. Dieses Modul fängt diese erkannten Befehle ab und spielt die passende Animation für Finja ab.
-   **Aktueller Stand der Anbindung:**
    -   Das `finja-chat` Projekt existiert bereits und ist die Basis.
    -   Es enthält zum Testen den Befehl `!drink`.
    -   Gibt ein Zuschauer `!drink` ein, gibt `finja-chat` aktuell nur den Text: `"Finja hat was zu trinken bekommen"` in der Konsole aus.
    -   **Ziel:** Dieses Modul wird dafür sorgen, dass bei `!drink` zusätzlich eine Animation abgespielt wird, in der Finja trinkt.
-   **Geplante Features:**
    -   **Animations-Mapping:** Eine einfache Logik, die Chat-Befehle (z.B. `!eat`) mit den passenden Animations-Dateinamen (z.B. `eat_apple.gif`) verknüpft.
    -   **Modulare Befehlserweiterung:** Neue Befehle können zuerst in `finja-chat` angelegt und dann hier einfach mit einer Animation verknüpft werden.

---

## 🚀 Zukunftsmusik & Geplante Erweiterungen

Die beiden oben genannten Module sind nur der Anfang! Es gibt bereits viele weitere Ideen, die in Zukunft umgesetzt werden könnten:

-   **Stimmungs-System:** Finjas Reaktionen könnten von ihrer aktuellen Stimmung (fröhlich, müde, mürrisch) abhängen.
-   **Stream-Alert-Integration:** Finja könnte auf Follows, Subs oder Raids mit besonderen Animationen reagieren.
-   **Punkte-System:** Zuschauer könnten Kanalpunkte ausgeben, um exklusive oder längere Animationen freizuschalten.

---

## 📌 Kombinierte Roadmap

Hier ist der grobe Fahrplan für die Entwicklung der ersten beiden Module:

-   [ ] **Grundlagen schaffen**
    -   [ ] Basis-Modstruktur für VPet erstellen.
    -   [ ] Eine stabile **API-Brücke zum `finja-chat` Modul** bauen, um erkannte Befehle zu empfangen.
-   [ ] **Technische Anbindung**
    -   [ ] Hook in das "Musik-Gehirn" für das Dance-Modul konzipieren.
-   [ ] **Erste Implementierungen**
    -   [ ] `!drink` mit einer ersten Platzhalter-Animation für das Trinken verknüpfen.
    -   [ ] Eine erste Test-Tanzanimation triggern.
-   [ ] **Stream-Integration & Feinschliff**
    -   [ ] Animationen im Stream korrekt darstellen.
    -   [ ] Auswahl-Logik für Tanz-Animationen basierend auf Genre entwickeln.

---

## 📜 Lizenz

MIT © 2025 – J. Apps  
**Dieses Projekt ist eine Sammlung von Platzhalter-Modulen und befindet sich aktiv in der Entwicklung.**

---

## 🆘 Support & Kontakt

Bei Fragen oder Problemen erreichst du uns hier:

-   **E-Mail:** contact@jappshome.de
-   **Website:** [jappshome.de](https://jappshome.de)
-   **Unterstützung:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)

---

🩷 _„I’ll do so much more soon… just you wait! 😗“_ – Finja