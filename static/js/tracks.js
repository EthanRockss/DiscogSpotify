(function () {
  const IO_ROOT_MARGIN = '800px';

  /* ---------------- Page data ---------------- */

  const body = document.body;
  const playlistId = body.dataset.playlistId;
  const limit = Number(body.dataset.pageLimit) || 100;

  if (!playlistId) {
    console.warn('tracks.js: missing playlistId');
    return;
  }

  /* ---------------- Lazy images ---------------- */

  let imgObserver = null;

  if ('IntersectionObserver' in window) {
    imgObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        const img = entry.target;
        const src = img.dataset.src;
        if (src) {
          img.src = src;
          img.onload = () => img.classList.add('loaded');
          img.removeAttribute('data-src');
        }
        observer.unobserve(img);
      });
    }, { rootMargin: '300px', threshold: 0.01 });
  }

  function observeImage(img) {
    if (!img?.dataset?.src) return;
    if (imgObserver) imgObserver.observe(img);
    else {
      img.src = img.dataset.src;
      img.onload = () => img.classList.add('loaded');
      img.removeAttribute('data-src');
    }
  }

  document.querySelectorAll('img[data-src]').forEach(observeImage);

  /* ---------------- Infinite load ---------------- */

  const btn = document.getElementById('load-more-tracks');
  const sentinel = document.getElementById('tracks-sentinel');
  const ul = document.getElementById('tracks-list');

  if (!ul) return;

  let isLoading = false;
  let offset = btn ? Number(btn.dataset.offset || 0) : limit;

  async function loadMore() {
    if (isLoading) return;
    isLoading = true;

    btn && (btn.disabled = true, btn.textContent = 'Loading...');

    try {
      const res = await fetch(
        `/spotify_playlist_tracks?playlist_id=${encodeURIComponent(playlistId)}&offset=${offset}&limit=${limit}`,
        { credentials: 'same-origin' }
      );

      if (!res.ok) throw new Error('Network error');

      const data = await res.json();
      const items = data.items || [];

      items.forEach(t => {
        const li = document.createElement('li');
        li.className = 'track';

        const thumb = document.createElement('div');
        thumb.className = 'thumb';

        if (t.album_img) {
          const img = document.createElement('img');
          img.dataset.src = t.album_img;
          img.loading = 'lazy';
          img.alt = 'album art';
          thumb.appendChild(img);
          observeImage(img);
        } else {
          thumb.innerHTML =
            '<svg width="48" height="48" viewBox="0 0 24 24" aria-hidden>' +
            '<rect width="24" height="24" rx="4" fill="rgba(255,255,255,0.03)"/>' +
            '</svg>';
        }

        const info = document.createElement('div');
        info.className = 'info';
        info.innerHTML = `
          <div class="name">${t.name || 'Unknown'}</div>
          <div class="artists">${t.artists || ''}</div>
        `;

        const action = document.createElement('div');
        action.className = 'action';

        const mkBtn = (url, text) => {
          const a = document.createElement('a');
          a.className = 'btn';
          a.href = url;
          a.target = '_blank';
          a.rel = 'noopener noreferrer';
          a.textContent = text;
          return a;
        };

        action.appendChild(mkBtn(t.discogs_url || '#', '🔎 Search Vinyl'));
        t.album_search_url && action.appendChild(mkBtn(t.album_search_url, '🎶 Search Album'));
        t.artist_search_url && action.appendChild(mkBtn(t.artist_search_url, '🎭 Search Artist'));

        li.append(thumb, info, action);
        ul.appendChild(li);
      });

      offset += items.length;

      if (!data.next_offset || items.length === 0) {
        btn?.remove();
        sentinel?.remove();
        observer?.disconnect();
      } else {
        btn && (
          btn.disabled = false,
          btn.textContent = 'Load more tracks',
          btn.dataset.offset = String(offset)
        );
      }
    } catch (err) {
      console.error(err);
      btn && (btn.disabled = false, btn.textContent = 'Load more tracks');
    } finally {
      isLoading = false;
    }
  }

  btn?.addEventListener('click', loadMore);

  let observer = null;
  if (sentinel && 'IntersectionObserver' in window) {
    observer = new IntersectionObserver(entries => {
      entries.forEach(e => e.isIntersecting && loadMore());
    }, { rootMargin: IO_ROOT_MARGIN, threshold: 0.01 });

    observer.observe(sentinel);
  }
})();
