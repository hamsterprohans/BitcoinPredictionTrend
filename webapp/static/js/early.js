// Dimuat sinkron di <head>: tandai sesi yang sudah melewati splash agar tak berkedip. Berkas sendiri (bukan inline) demi CSP ketat.
try { if (sessionStorage.getItem("splash-seen")) document.documentElement.classList.add("no-splash"); } catch (e) { /* penyimpanan diblokir: abaikan */ }
