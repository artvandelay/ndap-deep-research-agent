(function () {
  "use strict";

  window.FC = window.FC || {};

  const ALLOWED = { verified: true, unverified: true, contradicted: true };

  function emptyResult(claimId, note) {
    return {
      claimId: claimId,
      status: "unverified",
      ndapValue: "",
      unit: "",
      year: "",
      datasetId: "",
      datasetName: "",
      datasetUrl: "",
      note: note || "",
      evidenceCsv: "",
    };
  }

  async function verifyClaim(claim, options) {
    const deep = options && options.deep;
    const claimId = claim.id || "";
    try {
      const query = [claim.metric, claim.place, claim.year].filter(Boolean).join(" ") || claim.statement;
      const candidates = FC.core.searchIndex(query, 60);
      if (!candidates.length) {
        return emptyResult(claimId, "No NDAP dataset matches this claim.");
      }

      if (!FC.core.settings.proxy) {
        return emptyResult(claimId, "Row data unavailable (no proxy configured).");
      }

      const n = deep ? 3 : 1;
      const sel = await FC.core.selectDatasets(claim.statement, candidates, [], n);
      const picks = sel.picks || [];
      if (!picks.length) {
        return emptyResult(claimId, "No suitable NDAP dataset selected.");
      }

      const csvBlocks = [];
      for (const pick of picks) {
        try {
          const fetched = await FC.core.fetchDatasetRows(pick.id);
          const sub = FC.core.selectRelevantRows(fetched.rows, query, 40);
          csvBlocks.push(
            "Dataset " + pick.id + " (" + pick.name + ")\n"
            + FC.core.rowsToCsv(fetched.columns, sub)
          );
        } catch (_) {
          /* skip failed downloads */
        }
      }

      if (!csvBlocks.length) {
        return emptyResult(claimId, "Could not download NDAP rows.");
      }

      const messages = [
        { role: "system", content: FC.core.P("fc_verify_sys") },
        {
          role: "user",
          content: "Claim:\n" + JSON.stringify(claim) + "\n\nNDAP data:\n"
            + csvBlocks.join("\n\n") + "\n\nReturn JSON only.",
        },
      ];
      const p = FC.core.extractJson(await FC.core.orComplete(messages, 0, 700));
      let status = String(p.status || "unverified").toLowerCase();
      if (!ALLOWED[status]) status = "unverified";

      const datasetId = String(p.dataset_id || picks[0].id || "");
      const pickMatch = picks.find(function (x) { return String(x.id) === datasetId; }) || picks[0];

      return {
        claimId: claimId,
        status: status,
        ndapValue: String(p.ndap_value != null ? p.ndap_value : ""),
        unit: String(p.unit != null ? p.unit : ""),
        year: String(p.year != null ? p.year : ""),
        datasetId: datasetId,
        datasetName: pickMatch ? String(pickMatch.name || "") : "",
        datasetUrl: datasetId ? "https://ndap.niti.gov.in/dataset/" + datasetId : "",
        note: String(p.note != null ? p.note : ""),
        evidenceCsv: (csvBlocks[0] || "").slice(0, 2000),
      };
    } catch (err) {
      return emptyResult(claimId, "Verification error: " + String(err && err.message || err));
    }
  }

  async function verifyAll(claims, options) {
    const deep = options && options.deep;
    const onProgress = options && options.onProgress;
    const total = claims.length;
    const results = new Array(total);
    let done = 0;
    let nextIndex = 0;
    const concurrency = 3;

    async function worker() {
      while (nextIndex < total) {
        const i = nextIndex++;
        const claim = claims[i];
        const result = await verifyClaim(claim, { deep: deep });
        results[i] = result;
        done += 1;
        if (onProgress) onProgress(done, total, result);
      }
    }

    const workers = [];
    for (let w = 0; w < Math.min(concurrency, total); w++) {
      workers.push(worker());
    }
    await Promise.all(workers);
    return results;
  }

  FC.verify = {
    verifyClaim: verifyClaim,
    verifyAll: verifyAll,
  };
})();
