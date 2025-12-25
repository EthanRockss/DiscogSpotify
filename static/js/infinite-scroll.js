(() => {
  window.createInfiniteScroll = function ({
    sentinel,
    loadMore,
    rootMargin = '800px'
  }) {
    if (!sentinel || typeof loadMore !== 'function') {
      console.warn('InfiniteScroll: missing sentinel or loadMore');
      return null;
    }

    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            loadMore();
          }
        });
      }, { rootMargin, threshold: 0.01 });

      observer.observe(sentinel);
      return observer;
    }

    // Scroll fallback
    const onScroll = () => {
      const nearBottom =
        window.innerHeight + window.scrollY >=
        document.body.offsetHeight - 800;
      if (nearBottom) loadMore();
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return null;
  };
})();
