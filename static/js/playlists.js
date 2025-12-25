(() => {
  const pageLimit = Number(document.body.dataset.pageLimit) || 50;
  const grid = document.getElementById('playlists-grid');
  const btn = document.getElementById('load-more');
  const sentinel = document.getElementById('scroll-sentinel');

  let offset = btn ? Number(btn.dataset.offset || 0) : pageLimit;
  let isLoading = false;

  observeAllLazyImages();

  async function loadMore() {
    if (isLoading) return;
    isLoading = true;
    btn && (btn.disabled = true, btn.textContent = 'Loading...');

    try {
      const res = await fetch(`/spotify_playlists_data?offset=${offset}&limit=${pageLimit}`, {
        credentials: 'same-origin'
      });
      const data = await res.json();

      (data.items || []).forEach(p => {
        const img = p.image
          ? `<img data-src="${p.image}" loading="lazy" alt="playlist cover">`
          : `<svg width="72" height="72" aria-hidden><rect width="24" height="24" rx="4"/></svg>`;

        grid.insertAdjacentHTML('beforeend', `
          <div class="card">
            <div class="card-top">
              <div class="cover">${img}</div>
              <div class="card-content">
                <a class="title view-link" href="/spotify_playlist/${p.id}">
                  ${p.name || 'Untitled'}
                </a>
                <div class="meta">${p.tracks_total || 0} tracks</div>
              </div>
            </div>
          </div>
        `);
      });

      observeAllLazyImages(grid);
      offset += (data.items || []).length;

      if (!data.next) {
        btn?.remove();
        sentinel?.remove();
      } else {
        btn && (btn.disabled = false, btn.textContent = 'Load more playlists');
      }
    } finally {
      isLoading = false;
    }
  }

  btn?.addEventListener('click', loadMore);
  createInfiniteScroll({ sentinel, loadMore });
})();
