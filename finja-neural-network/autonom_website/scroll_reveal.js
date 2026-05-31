    // Scroll reveal
    const reveals = document.querySelectorAll('.reveal');
    const revealOnScroll = () => {
      reveals.forEach(el => {
        const top = el.getBoundingClientRect().top;
        if (top < window.innerHeight * 0.85) el.classList.add('visible');
      });
    };
    window.addEventListener('scroll', revealOnScroll);
    revealOnScroll();

    // Nav background on scroll
    const nav = document.querySelector('nav');
    window.addEventListener('scroll', () => {
      nav.style.background = window.scrollY > 50 ? 'rgba(5, 5, 8, 0.95)' : 'rgba(5, 5, 8, 0.8)';
    });