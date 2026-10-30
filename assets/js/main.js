(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hasIO = 'IntersectionObserver' in window;

  // Header hairline once the page scrolls
  const header = document.querySelector('.site-header');
  if (header) {
    const onScroll = () => header.classList.toggle('is-scrolled', window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  // Arriving from another page at a section (./#cena): land there at once. Inside a frame (the site
  // preview) the viewer can keep the scroll position of the page before, which opened a revír at its
  // bottom lists, so there a page without a section opens at its top. Checked again once images and
  // fonts have settled and shortly after, unless the visitor has already started scrolling.
  // Back/Forward and reload keep their position; a browser window on its own needs none of this
  const arrival = window.location.hash && document.getElementById(window.location.hash.slice(1));
  const navEntry = (window.performance && performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) || {};
  const toTop = !arrival && window.self !== window.top && navEntry.type !== 'back_forward' && navEntry.type !== 'reload';
  if (arrival || toTop) {
    let moved = false;
    ['wheel', 'touchstart', 'pointerdown', 'keydown'].forEach((type) => {
      window.addEventListener(type, () => { moved = true; }, { once: true, passive: true });
    });
    const land = () => {
      if (moved) return;
      if (!arrival && window.scrollY === 0) return;
      document.documentElement.style.scrollBehavior = 'auto';
      if (arrival) {
        arrival.scrollIntoView({ block: 'start' });
      } else {
        // The page's smooth scrolling would otherwise glide up from the bottom
        try { window.scrollTo({ top: 0, left: 0, behavior: 'instant' }); } catch (e) { window.scrollTo(0, 0); }
      }
      document.documentElement.style.scrollBehavior = '';
    };
    land();
    window.addEventListener('load', () => {
      land();
      [150, 500].forEach((ms) => window.setTimeout(land, ms));
    }, { once: true });
    if (document.fonts) document.fonts.ready.then(land);
  }

  // Menu: drop-down below 1024px, closes on a link, Esc, a tap outside or when focus leaves the header
  const nav = document.getElementById('site-nav');
  const navToggle = document.querySelector('[data-nav-toggle]');
  if (header && nav && navToggle) {
    const scrim = document.createElement('div');
    scrim.className = 'nav-scrim';
    scrim.hidden = true;
    header.after(scrim);
    const toggleLabel = navToggle.querySelector('.nav-toggle__label');
    const isOpen = () => navToggle.getAttribute('aria-expanded') === 'true';
    const setOpen = (open) => {
      navToggle.setAttribute('aria-expanded', String(open));
      if (toggleLabel) toggleLabel.textContent = open ? 'Zavrieť' : 'Menu';
      header.classList.toggle('nav-open', open);
      document.documentElement.classList.toggle('nav-open', open);
      scrim.hidden = !open;
    };
    navToggle.addEventListener('click', () => setOpen(!isOpen()));
    scrim.addEventListener('click', () => setOpen(false));
    nav.addEventListener('click', (e) => { if (e.target.closest('a')) setOpen(false); });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && isOpen()) { setOpen(false); navToggle.focus(); }
    });
    header.addEventListener('focusout', (e) => {
      if (isOpen() && e.relatedTarget && !header.contains(e.relatedTarget)) setOpen(false);
    });
    window.matchMedia('(min-width: 1024px)').addEventListener('change', () => setOpen(false));

    // Homepage: highlight the section on screen (the last one whose top passed 35 % of the viewport)
    const spy = Array.from(nav.querySelectorAll('a[href^="#"]'))
      .map((a) => [a, document.getElementById(a.hash.slice(1))])
      .filter(([, el]) => el);
    if (spy.length) {
      let queued = false;
      const mark = () => {
        queued = false;
        const line = window.innerHeight * 0.35;
        let current = spy[0][0];
        spy.forEach(([a, el]) => { if (el.getBoundingClientRect().top <= line) current = a; });
        spy.forEach(([a]) => a.classList.toggle('is-active', a === current));
      };
      const queue = () => { if (!queued) { queued = true; window.requestAnimationFrame(mark); } };
      window.addEventListener('scroll', queue, { passive: true });
      window.addEventListener('resize', queue);
      mark();
    }
  }

  // Hero: loop of "boundary draws, tap lands, revír card pops up", while the card is on screen
  const heroVisual = document.querySelector('.hero-visual');
  const heroTag = heroVisual && heroVisual.querySelector('.revir-tag');
  const loopToggle = heroVisual && heroVisual.querySelector('[data-loop-toggle]');
  if (heroTag && !reduceMotion) {
    const HOLD = 6200;  // from start until the card folds away
    const EXIT = 600;
    const GAP = 600;
    let timer = null;
    let inView = !hasIO;
    let paused = false;

    const clear = () => { window.clearTimeout(timer); timer = null; };
    const running = () => inView && !paused && !document.hidden;
    const play = () => {
      clear();
      heroVisual.classList.remove('is-live', 'is-leaving');
      void heroVisual.offsetWidth; // restart the CSS animations from the first frame
      heroVisual.classList.add('is-live');
      timer = window.setTimeout(() => {
        heroVisual.classList.add('is-leaving');
        timer = window.setTimeout(() => {
          heroVisual.classList.remove('is-live', 'is-leaving');
          timer = window.setTimeout(() => { timer = null; start(); }, GAP);
        }, EXIT);
      }, HOLD);
    };
    function start() { if (running() && !timer) play(); }

    if (hasIO) {
      new IntersectionObserver((entries) => {
        inView = entries[entries.length - 1].isIntersecting;
        if (inView) start(); else clear();
      }, { threshold: 0.6 }).observe(heroTag);
    } else {
      start();
    }
    document.addEventListener('visibilitychange', () => (document.hidden ? clear() : start()));

    if (loopToggle) {
      loopToggle.addEventListener('click', () => {
        paused = !paused;
        loopToggle.setAttribute('aria-pressed', String(paused));
        clear();
        heroVisual.classList.remove('is-live', 'is-leaving');
        heroVisual.classList.toggle('is-static', paused);
        start();
      });
    }
  }

  // Boundary map, looping like the hero while the map is on screen: the pins of "začiatok a koniec",
  // then the exact boundary draws and fills in, holds, winds back to the pins and starts over.
  // Choosing a view shows it a little longer and the loop goes on from there; only the pause button stops it
  const map = document.querySelector('[data-map]');
  if (map) {
    const buttons = document.querySelectorAll('[data-map-mode]');
    const status = document.querySelector('[data-map-status]');
    const mapToggle = map.querySelector('[data-map-toggle]');
    const messages = {
      pins: 'Len dva body na rieke. Nevidno, či prítok a štrkovisko patria do revíru, ani či ste v ňom.',
      polygon: 'Celá plocha revíru vrátane prítoku. Štrkovisko vedľa je iný revír.'
    };
    const STAY = { pins: 1700, polygon: 3400 }; // how long each view stays before the next one
    const FIRST = 700; // the first switch, once the map comes into view
    const PICKED = 2500; // extra time on a view someone chose
    let timer = null;
    let inView = !hasIO;
    let paused = reduceMotion;
    let played = false;

    // The loop changes the text silently; screen readers hear it only when someone picks a view
    const setMode = (mode, announce) => {
      map.dataset.mode = mode;
      buttons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mapMode === mode)));
      if (status) {
        status.setAttribute('aria-live', announce ? 'polite' : 'off');
        status.textContent = messages[mode];
      }
    };
    const clear = () => { window.clearTimeout(timer); timer = null; };
    const next = () => {
      setMode(map.dataset.mode === 'pins' ? 'polygon' : 'pins', false);
      timer = window.setTimeout(next, STAY[map.dataset.mode]);
    };
    const start = () => {
      if (timer || paused || !inView || document.hidden) return;
      timer = window.setTimeout(next, played ? STAY[map.dataset.mode] : FIRST);
      played = true;
    };
    const setPaused = (value) => {
      paused = value;
      map.classList.toggle('is-paused', value);
      if (mapToggle) mapToggle.setAttribute('aria-pressed', String(value));
      clear();
      start();
    };

    buttons.forEach((b) => b.addEventListener('click', () => {
      setMode(b.dataset.mapMode, true);
      clear();
      if (paused || !inView || document.hidden) return;
      played = true;
      timer = window.setTimeout(next, STAY[b.dataset.mapMode] + PICKED);
    }));

    if (!reduceMotion) {
      setMode('pins', false);
      if (hasIO) {
        new IntersectionObserver((entries) => {
          inView = entries[entries.length - 1].isIntersecting;
          if (inView) start(); else clear();
        }, { threshold: 0.6 }).observe(map);
      } else {
        start();
      }
      document.addEventListener('visibilitychange', () => (document.hidden ? clear() : start()));
      if (mapToggle) mapToggle.addEventListener('click', () => setPaused(!paused));
    }
  }

  // Screens tour tabs
  const tablist = document.querySelector('[role="tablist"]');
  if (tablist) {
    const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
    const select = (tab, focus) => {
      tabs.forEach((t) => {
        const on = t === tab;
        t.setAttribute('aria-selected', String(on));
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
      });
      if (focus) tab.focus();
    };
    tabs.forEach((tab, i) => {
      tab.addEventListener('click', () => select(tab));
      tab.addEventListener('keydown', (e) => {
        const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        let next;
        if (step) next = tabs[(i + step + tabs.length) % tabs.length];
        else if (e.key === 'Home') next = tabs[0];
        else if (e.key === 'End') next = tabs[tabs.length - 1];
        if (next) {
          e.preventDefault();
          select(next, true);
        }
      });
    });
  }

  // Sticky buy bar on phones: hidden while another buy button or the footer is on screen
  const sticky = document.querySelector('[data-sticky]');
  const cookie = document.getElementById('cookie');
  const onScreen = new Set();
  const updateSticky = () => {
    if (!sticky) return;
    const show = onScreen.size === 0 && (!cookie || cookie.hidden);
    sticky.classList.toggle('is-visible', show);
    sticky.inert = !show;
  };
  if (sticky && hasIO) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => (e.isIntersecting ? onScreen.add(e.target) : onScreen.delete(e.target)));
      updateSticky();
    });
    document.querySelectorAll('[data-sticky-hide]').forEach((el) => io.observe(el));
  }

  // Cookie consent; Google Analytics loads only after consent
  const GA_ID = 'G-B3J9SKG24G';
  const KEY = 'rr-cookie-consent';
  const store = {
    get() { try { return window.localStorage.getItem(KEY); } catch (e) { return null; } },
    set(v) { try { window.localStorage.setItem(KEY, v); } catch (e) { /* storage blocked */ } }
  };
  let gaLoaded = false;
  const loadGA = () => {
    if (gaLoaded) {
      window.gtag('consent', 'update', { analytics_storage: 'granted' });
      return;
    }
    gaLoaded = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', GA_ID);
    const s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
    document.head.appendChild(s);
  };
  const showCookie = (show) => {
    if (!cookie) return;
    cookie.hidden = !show;
    updateSticky();
  };

  const choice = store.get();
  if (choice === 'granted') loadGA();
  else if (!choice) showCookie(true);

  if (cookie) {
    cookie.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-consent]');
      if (!btn) return;
      const value = btn.dataset.consent;
      store.set(value);
      if (value === 'granted') loadGA();
      else if (gaLoaded) window.gtag('consent', 'update', { analytics_storage: 'denied' });
      showCookie(false);
    });
  }
  document.querySelectorAll('[data-cookie-open]').forEach((b) => b.addEventListener('click', () => {
    showCookie(true);
    const first = cookie && cookie.querySelector('button');
    if (first) first.focus();
  }));

  // Track which buy button sends people to Google Play
  document.addEventListener('click', (e) => {
    const cta = e.target.closest('[data-cta]');
    if (cta && gaLoaded) {
      window.gtag('event', 'play_store_click', { cta_position: cta.dataset.cta, transport_type: 'beacon' });
    }
  });

  document.querySelectorAll('[data-year]').forEach((el) => { el.textContent = String(new Date().getFullYear()); });
})();
