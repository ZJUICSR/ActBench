document.addEventListener('DOMContentLoaded', () => {
  const burger = document.querySelector('.navbar-burger');
  const menu = document.getElementById('site-nav');

  if (burger && menu) {
    burger.addEventListener('click', () => {
      const active = menu.classList.toggle('is-active');
      burger.setAttribute('aria-expanded', String(active));
    });

    menu.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        menu.classList.remove('is-active');
        burger.setAttribute('aria-expanded', 'false');
      });
    });
  }

  document.querySelectorAll('[data-copy-target]').forEach((button) => {
    button.addEventListener('click', async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;
      const previous = button.textContent;
      try {
        await navigator.clipboard.writeText(target.innerText);
        button.textContent = 'Copied';
      } catch (_) {
        button.textContent = 'Select text';
      }
      window.setTimeout(() => { button.textContent = previous; }, 1600);
    });
  });
});
