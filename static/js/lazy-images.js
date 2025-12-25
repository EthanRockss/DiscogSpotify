(() => {
  let observer = null;

  if ('IntersectionObserver' in window) {
    observer = new IntersectionObserver((entries, obs) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        const img = entry.target;
        const src = img.dataset.src;
        if (!src) return;

        img.src = src;
        img.onload = () => img.classList.add('loaded');
        img.removeAttribute('data-src');
        obs.unobserve(img);
      });
    }, { rootMargin: '300px', threshold: 0.01 });
  }

  window.observeLazyImage = function (img) {
    if (!img?.dataset?.src) return;
    if (observer) observer.observe(img);
    else {
      img.src = img.dataset.src;
      img.onload = () => img.classList.add('loaded');
      img.removeAttribute('data-src');
    }
  };

  window.observeAllLazyImages = function (root = document) {
    root.querySelectorAll('img[data-src]').forEach(window.observeLazyImage);
  };
})();
