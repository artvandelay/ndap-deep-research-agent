(function () {
  "use strict";

  window.FC = window.FC || {};

  const CLAIM_FIELDS = [
    "quote",
    "statement",
    "type",
    "metric",
    "place",
    "year",
    "value",
    "unit"
  ];

  function coerceString(v) {
    if (v === null || v === undefined) return "";
    if (typeof v === "string") return v;
    return String(v);
  }

  async function extractClaims(articleText) {
    try {
      const messages = [
        { role: "system", content: FC.core.P("fc_extract_sys") },
        {
          role: "user",
          content: "Article:\n" + articleText + "\n\nReturn JSON only."
        }
      ];
      const parsed = FC.core.extractJson(
        await FC.core.orComplete(messages, 0.1, 1500)
      );
      const rawClaims = Array.isArray(parsed && parsed.claims)
        ? parsed.claims
        : [];
      const claims = [];
      for (let i = 0; i < rawClaims.length; i++) {
        const raw = rawClaims[i] || {};
        const claim = { id: "c" + (i + 1) };
        for (const field of CLAIM_FIELDS) {
          claim[field] = coerceString(raw[field]);
        }
        if (!claim.quote) continue;
        claims.push(claim);
        if (claims.length >= 15) break;
      }
      return claims;
    } catch (err) {
      return [];
    }
  }

  FC.extract = { extractClaims: extractClaims };
})();
