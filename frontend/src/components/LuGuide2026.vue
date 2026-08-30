<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import LuEditionSeal from "./LuEditionSeal.vue";
import LuEvaluationCompass from "./LuEvaluationCompass.vue";
import LuRainMark from "./LuRainMark.vue";

const guide = ref(null);
const loadingError = ref("");
const introVisible = ref(false);
const introLeaving = ref(false);
const menuOpen = ref(false);
const previousDocument = { title: document.title, lang: document.documentElement.lang };
const timers = new Set();
let revealObserver = null;

const isReleased = computed(() => guide.value?.status === "released");
const dataUrl = new URL("data/guides/2026.json", `${window.location.origin}${import.meta.env.BASE_URL}`).href;

function schedule(callback, delay) {
  const timer = window.setTimeout(() => {
    timers.delete(timer);
    callback();
  }, delay);
  timers.add(timer);
}

function dismissIntro() {
  introLeaving.value = true;
  schedule(() => {
    introVisible.value = false;
    document.body.classList.remove("lu-intro-active");
  }, 420);
}

function setupIntro() {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const alreadyPlayed = sessionStorage.getItem("luGuide2026IntroPlayed") === "true";
  if (reducedMotion || alreadyPlayed) return;
  introVisible.value = true;
  document.body.classList.add("lu-intro-active");
  sessionStorage.setItem("luGuide2026IntroPlayed", "true");
  schedule(dismissIntro, 2600);
}

function scrollToSection(id) {
  menuOpen.value = false;
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setMeta(name, content) {
  let element = document.head.querySelector(`meta[name="${name}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute("name", name);
    element.dataset.luGuide = "true";
    document.head.appendChild(element);
  }
  element.setAttribute("content", content);
}

function setupReveal() {
  const elements = document.querySelectorAll(".lu-guide [data-reveal]");
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    elements.forEach((element) => element.classList.add("is-visible"));
    return;
  }
  revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      revealObserver.unobserve(entry.target);
    });
  }, { rootMargin: "0px 0px -12%", threshold: 0.12 });
  elements.forEach((element) => revealObserver.observe(element));
}

async function loadGuide() {
  loadingError.value = "";
  try {
    const response = await fetch(dataUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    guide.value = await response.json();
    document.title = `吕其林指南 ${guide.value.edition} | DuskRain Food Map`;
    setMeta("description", "DuskRain Food Map 2026 年度个人美食指南，记录真实到店体验，并于 2027 年 1 月正式发布。");
    await nextTick();
    setupReveal();
    if (window.location.pathname.includes("/archive")) schedule(() => scrollToSection("archives"), 120);
  } catch (error) {
    loadingError.value = "这一版指南暂时无法载入，请稍后重试。";
    console.error("Impossible de charger les données du Guide de Lü", error);
  }
}

onMounted(() => {
  document.body.classList.add("lu-guide-open");
  document.documentElement.classList.add("lu-guide-open");
  document.documentElement.lang = "zh-CN";
  setupIntro();
  loadGuide();
});

onBeforeUnmount(() => {
  timers.forEach((timer) => window.clearTimeout(timer));
  revealObserver?.disconnect();
  document.body.classList.remove("lu-guide-open", "lu-intro-active");
  document.documentElement.classList.remove("lu-guide-open");
  document.title = previousDocument.title;
  document.documentElement.lang = previousDocument.lang;
  document.head.querySelectorAll('[data-lu-guide="true"]').forEach((element) => element.remove());
});
</script>

<template>
  <div class="lu-guide">
    <Transition name="lu-intro">
      <div v-if="introVisible" class="lu-ceremony" :class="{ 'is-leaving': introLeaving }" role="dialog" aria-label="Ouverture de l’édition 2026">
        <button type="button" class="lu-intro-skip" @click="dismissIntro">Passer</button>
        <div class="lu-ceremony-line"></div>
        <div class="lu-ceremony-mark"><LuRainMark :count="1" /></div>
        <p>DuskRain Food Map</p>
        <strong>2026</strong>
        <span>Le Guide de Lü</span>
      </div>
    </Transition>

    <header v-if="guide" class="lu-nav">
      <a class="lu-nav-brand" href="/food-map/guide/2026/" aria-label="DuskRain，吕其林指南 2026">
        <LuRainMark :count="1" />
        <span><strong>DuskRain</strong><small>Le Guide de Lü · 2026</small></span>
      </a>
      <button class="lu-menu-button" type="button" :aria-expanded="String(menuOpen)" aria-controls="luNavigation" @click="menuOpen = !menuOpen">
        <span></span><span></span><b>Menu</b>
      </button>
      <nav id="luNavigation" :class="{ 'is-open': menuOpen }" aria-label="Navigation principale">
        <button type="button" @click="scrollToSection('edition')">{{ guide.navigation.edition }}</button>
        <button type="button" @click="scrollToSection('distinctions')">{{ guide.navigation.distinctions }}</button>
        <button type="button" @click="scrollToSection('methode')">{{ guide.navigation.methodology }}</button>
        <button type="button" @click="scrollToSection('archives')">{{ guide.navigation.archive }}</button>
        <a href="/food-map/">{{ guide.navigation.back }}</a>
      </nav>
    </header>

    <main v-if="guide">
      <section id="edition" class="lu-hero">
        <div class="lu-rain-curtain" aria-hidden="true"></div>
        <div class="lu-hero-aside" aria-hidden="true"><span>01</span><i></i><small>2026 — 2027</small></div>
        <div class="lu-hero-inner">
          <p class="lu-eyebrow">{{ guide.hero.eyebrow }}</p>
          <p class="lu-hero-kicker">{{ guide.hero.kicker }}</p>
          <div class="lu-hero-year">{{ guide.edition }}</div>
          <h1>{{ guide.hero.titleZh }}</h1>
          <p class="lu-signature">{{ guide.hero.signature }}</p>
          <p class="lu-hero-wordmark">{{ guide.hero.title }}</p>
          <div class="lu-fine-divider" aria-hidden="true"><span></span><LuRainMark :count="1" /><span></span></div>
          <p class="lu-publication">Édition {{ guide.edition }} · {{ guide.hero.publication }}</p>
          <h2>{{ isReleased ? guide.hero.releasedTitle : guide.hero.teaserTitle }}</h2>
          <p class="lu-hero-body">{{ isReleased ? guide.hero.releasedBody : guide.hero.teaserBody }}</p>
          <div class="lu-hero-actions">
            <button type="button" class="lu-button lu-button-primary" @click="scrollToSection(isReleased ? 'selection' : 'invitation')">{{ isReleased ? guide.hero.primaryReleased : guide.hero.primaryTeaser }}</button>
            <button type="button" class="lu-button lu-button-quiet" @click="scrollToSection('methode')">{{ guide.hero.secondary }}</button>
          </div>
          <p class="lu-period">{{ guide.hero.periodLabel }}</p>
        </div>
        <button class="lu-scroll-cue" type="button" aria-label="Continuer vers l’invitation" @click="scrollToSection('invitation')"><span></span>Faire défiler</button>
      </section>

      <section id="invitation" class="lu-paper-section lu-invitation">
        <div class="lu-section-number">02</div>
        <div class="lu-invitation-seal" data-reveal><LuEditionSeal :edition="guide.edition" /><p class="lu-signature">{{ guide.hero.signature }}</p></div>
        <div class="lu-invitation-copy" data-reveal>
          <p class="lu-eyebrow">{{ guide.invitation.eyebrow }}</p>
          <h2>{{ guide.invitation.title }}</h2>
          <p v-for="paragraph in guide.invitation.paragraphs" :key="paragraph">{{ paragraph }}</p>
          <strong>{{ guide.invitation.closing }}</strong>
        </div>
      </section>

      <section class="lu-ink-section lu-manifesto">
        <div class="lu-section-number">03</div>
        <div class="lu-manifesto-heading" data-reveal><p class="lu-eyebrow">{{ guide.manifesto.eyebrow }}</p><h2>{{ guide.manifesto.title }}</h2></div>
        <div class="lu-manifesto-body" data-reveal>
          <p>{{ guide.manifesto.body }}</p>
          <ol><li v-for="(principle, index) in guide.manifesto.principles" :key="principle"><span>0{{ index + 1 }}</span>{{ principle }}</li></ol>
        </div>
      </section>

      <section class="lu-paper-section lu-categories">
        <div class="lu-section-number">04</div>
        <div class="lu-section-heading" data-reveal><p class="lu-eyebrow">{{ guide.categories.eyebrow }}</p><h2>{{ guide.categories.title }}</h2><p>{{ guide.categories.intro }}</p></div>
        <div class="lu-category-grid">
          <article v-for="item in guide.categories.items" :key="item.number" data-reveal>
            <span>{{ item.number }}</span><div class="lu-category-glyph" aria-hidden="true"><i></i><i></i><i></i></div><h3>{{ item.name }}</h3><small class="lu-item-fr">{{ item.labelFr }}</small><p>{{ item.description }}</p>
          </article>
        </div>
      </section>

      <section id="distinctions" class="lu-ink-section lu-distinction-section">
        <div class="lu-section-number">05</div>
        <div class="lu-section-heading lu-section-heading-light" data-reveal><p class="lu-eyebrow">{{ guide.distinctions.eyebrow }}</p><h2>{{ guide.distinctions.title }}</h2><p>{{ guide.distinctions.intro }}</p></div>
        <div class="lu-distinction-grid">
          <article v-for="item in guide.distinctions.items" :key="item.id" data-reveal>
            <LuRainMark :count="item.count" :variant="item.id === 'rain-pick' ? 'rain-pick' : item.id === 'selected' ? 'selected' : 'drops'" />
            <p class="lu-distinction-index">{{ item.id === 'rain-pick' ? '04' : item.id === 'selected' ? '05' : `0${item.count}` }}</p>
            <h3>{{ item.name }}</h3><small class="lu-item-fr">{{ item.labelFr }}</small><strong>{{ item.definition }}</strong><p>{{ item.detail }}</p>
          </article>
        </div>
      </section>

      <section id="methode" class="lu-paper-section lu-methodology">
        <div class="lu-section-number">06</div>
        <div class="lu-methodology-intro" data-reveal><p class="lu-eyebrow">{{ guide.methodology.eyebrow }}</p><h2>{{ guide.methodology.title }}</h2><p>{{ guide.methodology.intro }}</p><LuEvaluationCompass /></div>
        <div class="lu-method-list">
          <article v-for="item in guide.methodology.items" :key="item.number" data-reveal><span>{{ item.number }}</span><h3>{{ item.name }}</h3><p>{{ item.description }}</p></article>
        </div>
        <p class="lu-method-note" data-reveal>{{ guide.methodology.note }}</p>
      </section>

      <section class="lu-ink-section lu-score-selection">
        <div class="lu-section-number">07</div>
        <div class="lu-score-heading" data-reveal><p class="lu-eyebrow">{{ guide.scoreSelection.eyebrow }}</p><h2>{{ guide.scoreSelection.title }}</h2></div>
        <div class="lu-score-copy" data-reveal><p>{{ guide.scoreSelection.body }}</p><strong>{{ guide.scoreSelection.statement }}</strong><p>{{ guide.scoreSelection.note }}</p></div>
      </section>

      <section class="lu-annual-section">
        <div class="lu-annual-mark" aria-hidden="true"><LuRainMark :count="1" /></div>
        <div data-reveal><p class="lu-eyebrow">{{ guide.annual.eyebrow }}</p><h2>{{ guide.annual.title }}</h2><p class="lu-annual-policy">{{ guide.annual.independence }}</p><p>{{ guide.annual.body }}</p></div>
      </section>

      <section id="selection" class="lu-release-section">
        <div class="lu-release-frame" data-reveal>
          <p class="lu-eyebrow">{{ isReleased ? guide.release.releasedEyebrow : guide.release.teaserEyebrow }}</p>
          <LuEditionSeal :edition="guide.edition" />
          <h2>{{ isReleased ? guide.release.releasedTitle : guide.release.teaserTitle }}</h2>
          <p>{{ isReleased ? guide.release.releasedBody : guide.release.teaserBody }}</p>
          <dl v-if="!isReleased">
            <div><dt>Période</dt><dd>01.01 — 31.12.2026</dd></div>
            <div><dt>Publication</dt><dd>Janvier 2027</dd></div>
            <div><dt>Formats</dt><dd>4 catégories</dd></div>
          </dl>
          <div v-else-if="!guide.entries.length" class="lu-empty-selection">这一版还没有公开的入选店铺。</div>
          <div v-else class="lu-entry-grid"><article v-for="entry in guide.entries" :key="entry.id"><span>{{ entry.city }} · {{ entry.category }}</span><h3>{{ entry.name }}</h3><p>{{ entry.summary }}</p></article></div>
          <a class="lu-button lu-button-primary" href="/food-map/">{{ guide.release.back }}</a>
        </div>
      </section>

      <section id="archives" class="lu-paper-section lu-archive-section">
        <div class="lu-section-number">08</div>
        <div class="lu-archive-copy" data-reveal><p class="lu-eyebrow">{{ guide.archive.eyebrow }}</p><h2>{{ guide.archive.title }}</h2><p>{{ guide.archive.description }}</p></div>
        <a class="lu-volume" href="/food-map/guide/2026/" data-reveal><span>{{ guide.edition }}</span><strong>Le Guide de Lü</strong><small>{{ guide.archive.label }}</small></a>
      </section>
    </main>

    <div v-else-if="loadingError" class="lu-load-error" role="alert"><LuRainMark :count="1" /><p>{{ loadingError }}</p><button type="button" class="lu-button lu-button-primary" @click="loadGuide">重试</button></div>

    <footer v-if="guide" class="lu-footer">
      <div class="lu-footer-brand"><strong>DuskRain</strong><span>{{ guide.hero.signature }}</span></div>
      <p class="lu-footer-tagline">{{ guide.footer.tagline }}</p>
      <div class="lu-footer-legal"><p>{{ guide.footer.disclaimer }}</p><p>{{ guide.footer.experience }}</p></div>
      <div class="lu-footer-bottom"><span>© DuskRain Food Map</span><span>Édition {{ guide.edition }}</span></div>
    </footer>
  </div>
</template>

<style src="../guide.css"></style>
