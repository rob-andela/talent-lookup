/*
 * andela_lookup_console.js
 * ------------------------
 * Quick ad-hoc lookup that runs entirely in your browser DevTools console
 * on a tab you are already signed in to (https://app.andela.com/...).
 *
 * NO INSTALL REQUIRED. Use this when you just want results once and don't
 * want to set up Python/Playwright.
 *
 *   1. Open https://app.andela.com/jobs and sign in.
 *   2. Open the search overlay (last button on the left sidebar) so the
 *      search input is visible on screen.
 *   3. Open DevTools (Cmd+Option+I on Mac), go to the Console tab.
 *   4. Edit the EMAILS array below, then paste the whole block and press
 *      Enter. Wait for it to finish - results print as a TSV block you
 *      can copy straight into a spreadsheet.
 */

(async () => {
    // --------- EDIT THIS LIST ---------
    const EMAILS = [
        // ['Display Name', 'email@example.com'],
        ['Lawrence Enehizena', 'lawstands@gmail.com'],
        ['Olugbenga Solomon Falodun', 'falodunosolomon@gmail.com'],
    ];
    // ----------------------------------

    const SEARCH_POLL_TIMEOUT_MS = 3000;  // Max time to wait for search results
    const PROFILE_POLL_TIMEOUT_MS = 2000;  // Max time to wait for status text
    const POLL_INTERVAL_MS = 100;          // Check every 100ms
    const SEARCH_DEBOUNCE_MS = 2000;       // Wait for server-side search to respond

    const setSearchValue = (value) => {
        const input = document.querySelector('input[placeholder*="Search"]');
        if (!input) throw new Error('Search input not visible. Open the search overlay first.');
        input.focus();
        // Clear previous value first
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(input, '');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        // Set new value
        setter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
    };

    const wait = (ms) => new Promise((r) => setTimeout(r, ms));

    const pollUntil = async (checkFn, timeoutMs, intervalMs = 100) => {
        const start = Date.now();
        while (Date.now() - start < timeoutMs) {
            const result = checkFn();
            if (result) return result;
            await wait(intervalMs);
        }
        return checkFn(); // Final check
    };

    const extractLinks = () =>
        Array.from(document.querySelectorAll('a[href^="/talent/"]'))
            .map((a) => ({ href: a.href, text: a.textContent.trim() }));

    const waitForSearchResults = async () => {
        // Poll until we get results or timeout
        return await pollUntil(
            () => {
                const links = extractLinks();
                return links.length > 0 ? links : null;
            },
            SEARCH_POLL_TIMEOUT_MS,
            POLL_INTERVAL_MS
        );
    };

    const detectStatus = (text) => {
        if (/Talent is in progress of being certified/i.test(text))
            return 'SKIP - certification in progress';
        if (/failed certification/i.test(text) && /can be reconsidered/i.test(text))
            return 'SKIP - failed certification, can be reconsidered';
        if (/deactivated/i.test(text)) return 'SKIP - deactivated';
        if (/disbanded/i.test(text)) return 'SKIP - disbanded';
        if (/Not Certified/.test(text)) return 'Not Certified';
        if (/Certified/.test(text)) return 'Certified';
        return 'Status unknown';
    };

    const verifyStatus = async (url) => {
        // Open profile in a hidden iframe so we don't lose the search overlay.
        const frame = document.createElement('iframe');
        frame.style.cssText = 'position:fixed;left:-9999px;width:1200px;height:800px;';
        frame.src = url;
        document.body.appendChild(frame);
        try {
            // Wait for iframe to load
            await new Promise((res) =>
                frame.addEventListener('load', res, { once: true })
            );
            // Poll for status text to appear (faster than fixed 3.5s wait)
            const status = await pollUntil(
                () => {
                    const text = frame.contentDocument?.body?.innerText || '';
                    const detected = detectStatus(text);
                    // Return if we found a definitive status (not "unknown")
                    if (detected !== 'Status unknown') return detected;
                    return null;
                },
                PROFILE_POLL_TIMEOUT_MS,
                POLL_INTERVAL_MS
            );
            // If still unknown, return the final check
            if (status) return status;
            const text = frame.contentDocument?.body?.innerText || '';
            return detectStatus(text);
        } finally {
            frame.remove();
        }
    };

    const rows = [['#', 'Name', 'Email', 'Andela Profile URL', 'Status']];
    console.log(`Looking up ${EMAILS.length} profiles ...`);

    for (let i = 0; i < EMAILS.length; i++) {
        const [name, email] = EMAILS[i];
        const idx = i + 1;
        try {
            setSearchValue(email);
            await wait(SEARCH_DEBOUNCE_MS); // Wait for server-side search
            const links = await waitForSearchResults();
            if (!links || !links.length) {
                rows.push([idx, name, email, 'NOT FOUND', 'No matches in ATC search']);
                console.log(`[${idx}/${EMAILS.length}] ${name}: not found`);
                continue;
            }
            // Pick first eligible match; fall back to first if all are skipped.
            let pickedUrl = links[0].href;
            let pickedStatus = null;
            for (const link of links) {
                const status = await verifyStatus(link.href);
                if (pickedStatus === null) {
                    pickedUrl = link.href;
                    pickedStatus = status;
                }
                if (!status.startsWith('SKIP') && status !== 'Status unknown') {
                    pickedUrl = link.href;
                    pickedStatus = status;
                    break;
                }
            }
            rows.push([idx, name, email, pickedUrl, pickedStatus]);
            console.log(`[${idx}/${EMAILS.length}] ${name}: ${pickedStatus}`);
        } catch (err) {
            rows.push([idx, name, email, 'ERROR', String(err).slice(0, 200)]);
            console.warn(`[${idx}/${EMAILS.length}] ${name}: ERROR ${err}`);
        }
    }

    const tsv = rows.map((r) => r.join('\t')).join('\n');
    console.log('\n===== RESULTS (copy block below into a spreadsheet) =====\n');
    console.log(tsv);
    try {
        await navigator.clipboard.writeText(tsv);
        console.log('\n(TSV also copied to your clipboard.)');
    } catch (_) {
        /* clipboard write requires user gesture in some browsers */
    }
    return rows;
})();
