function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeUrl(value) {
  const url = String(value ?? "").trim();
  return /^https?:\/\//i.test(url) ? url : "";
}

function renderInline(text) {
  const source = String(text ?? "");
  const pattern = /(\*\*([^*]+)\*\*|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g;
  let html = "";
  let lastIndex = 0;
  let match;

  while ((match = pattern.exec(source)) !== null) {
    html += escapeHtml(source.slice(lastIndex, match.index));
    if (match[2]) {
      html += `<strong>${escapeHtml(match[2])}</strong>`;
    } else if (match[3] && safeUrl(match[4])) {
      const url = escapeHtml(match[4]);
      html += `<a href="${url}" target="_blank" rel="noopener noreferrer">${escapeHtml(match[3])}</a>`;
    } else {
      html += escapeHtml(match[0]);
    }
    lastIndex = match.index + match[0].length;
  }

  html += escapeHtml(source.slice(lastIndex));
  return html;
}

function isBlockStart(line) {
  return (
    /^\s{0,3}#{1,3}\s+/.test(line)
    || /^\s{0,3}>\s?/.test(line)
    || /^\s{0,3}[-*]\s+/.test(line)
    || /^\s*!\[[^\]]*]\(https?:\/\/[^)\s]+\)\s*$/.test(line)
  );
}

export function renderReviewHtml(markdown) {
  const lines = String(markdown ?? "").replace(/\r\n?/g, "\n").split("\n");
  const html = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    const image = trimmed.match(/^!\[([^\]]*)]\((https?:\/\/[^)\s]+)\)$/);
    if (image && safeUrl(image[2])) {
      html.push(`<figure><img src="${escapeHtml(image[2])}" alt="${escapeHtml(image[1])}" loading="lazy"><figcaption>${escapeHtml(image[1])}</figcaption></figure>`);
      index += 1;
      continue;
    }

    const heading = line.match(/^\s{0,3}(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 4);
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^\s{0,3}[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s{0,3}[-*]\s+/.test(lines[index])) {
        items.push(`<li>${renderInline(lines[index].replace(/^\s{0,3}[-*]\s+/, ""))}</li>`);
        index += 1;
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    if (/^\s{0,3}>\s?/.test(line)) {
      const quotes = [];
      while (index < lines.length && /^\s{0,3}>\s?/.test(lines[index])) {
        quotes.push(renderInline(lines[index].replace(/^\s{0,3}>\s?/, "")));
        index += 1;
      }
      html.push(`<blockquote>${quotes.join("<br>")}</blockquote>`);
      continue;
    }

    const paragraph = [];
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines[index])) {
      paragraph.push(renderInline(lines[index].trim()));
      index += 1;
    }
    html.push(`<p>${paragraph.join("<br>")}</p>`);
  }

  return html.join("");
}
