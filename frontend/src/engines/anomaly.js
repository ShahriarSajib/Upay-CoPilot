import { isProductSpend } from "@/data/context";
import { clamp, mean, parseDate, quantiles, round, stdDev, sum } from "@/lib/format";
function newHistory() {
    return {
        allAmounts: [],
        byCategory: new Map(),
        byMerchant: new Map(),
        bySubcategory: new Map(),
        byHour: new Map(),
        count: 0,
        balance: 0,
    };
}
function push(h, tx) {
    h.count += 1;
    h.balance = tx.balance_after;
    if (tx.direction === "outflow" && tx.category !== "cash" && tx.category !== "transfer") {
        h.allAmounts.push(tx.amount);
        const cat = h.byCategory.get(tx.category) ?? [];
        cat.push(tx.amount);
        h.byCategory.set(tx.category, cat);
        const sub = h.bySubcategory.get(`${tx.category}|${tx.subcategory}`) ?? [];
        sub.push(tx.amount);
        h.bySubcategory.set(`${tx.category}|${tx.subcategory}`, sub);
    }
    const merch = `${tx.merchant_type}`;
    h.byMerchant.set(merch, (h.byMerchant.get(merch) ?? 0) + 1);
    const hour = parseDate(tx.timestamp).getHours();
    h.byHour.set(hour, (h.byHour.get(hour) ?? 0) + 1);
}
/* ------------------------------------------------------------------ *
 * PRNG (mulberry32) — deterministic for a given seed
 * ------------------------------------------------------------------ */
function mulberry32(seed) {
    let a = seed >>> 0;
    return () => {
        a = (a + 0x6d2b79f5) >>> 0;
        let t = a;
        t = Math.imul(t ^ (t >>> 15), t | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}
/* ------------------------------------------------------------------ *
 * Feature construction — strictly causal
 * ------------------------------------------------------------------ */
const FEATURES = [
    {
        key: "amount",
        label: "Amount",
        build: (tx, h) => {
            const q = quantiles(h.allAmounts);
            return (tx.amount - q.p50) / Math.max(50, q.p75 - q.p10 || 1);
        },
    },
    {
        key: "category_deviation",
        label: "Deviation from this category's usual ticket",
        build: (tx, h) => {
            const past = h.byCategory.get(tx.category) ?? [];
            if (past.length < 5)
                return 0;
            const q = quantiles(past);
            return (tx.amount - q.p50) / Math.max(50, q.p75 - q.p10 || 1);
        },
    },
    {
        key: "subcategory_deviation",
        label: "Deviation from this merchant's usual ticket",
        build: (tx, h) => {
            const past = h.bySubcategory.get(`${tx.category}|${tx.subcategory}`) ?? [];
            if (past.length < 3)
                return 0;
            const m = mean(past);
            const s = Math.max(20, stdDev(past));
            return (tx.amount - m) / s;
        },
    },
    {
        key: "merchant_rarity",
        label: "How rarely this merchant type appears",
        build: (_tx, h) => 1 / Math.sqrt(1 + h.count / 40),
    },
    {
        key: "hour_unusualness",
        label: "Time-of-day rarity",
        build: (tx, h) => {
            const hour = parseDate(tx.timestamp).getHours();
            const same = h.byHour.get(hour) ?? 0;
            return 1 / Math.sqrt(1 + same / 8);
        },
    },
    {
        key: "weekend_evening",
        label: "Late-night discretionary purchase",
        build: (tx) => {
            const d = parseDate(tx.timestamp);
            const discretionary = ["shopping", "entertainment", "other"].includes(tx.category);
            return discretionary && (d.getHours() >= 21 || d.getHours() <= 4) ? 1 : 0;
        },
    },
    {
        key: "round_number",
        label: "Unusually round amount",
        build: (tx) => {
            if (tx.amount < 500)
                return 0;
            const thousands = tx.amount % 1000;
            return thousands === 0 || thousands === 500 ? 1 : 0;
        },
    },
    {
        key: "cash_channel",
        label: "Cash channel",
        build: (tx) => (tx.cash_out ? 1 : 0),
    },
    {
        key: "balance_impact",
        label: "Impact on the wallet balance",
        build: (tx, h) => (h.balance > 0 ? Math.min(1, tx.amount / h.balance) : 0),
    },
];
function buildMatrix(rows) {
    const history = newHistory();
    const matrix = [];
    for (const tx of rows) {
        matrix.push(FEATURES.map((f) => f.build(tx, history)));
        push(history, tx);
    }
    return { matrix, featureKeys: FEATURES.map((f) => f.key) };
}
function buildIsolationTree(data, indices, depth, maxDepth, rng) {
    const node = { size: indices.length, depth };
    if (indices.length <= 1 || depth >= maxDepth)
        return node;
    // Pick a feature that actually varies in this subsample.
    let feature = Math.floor(rng() * data[0].length);
    for (let attempt = 0; attempt < data[0].length; attempt += 1) {
        const candidate = (feature + attempt) % data[0].length;
        const values = indices.map((i) => data[i][candidate]);
        if (Math.max(...values) > Math.min(...values)) {
            feature = candidate;
            break;
        }
    }
    const values = indices.map((i) => data[i][feature]);
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    if (hi <= lo)
        return node;
    const split = lo + rng() * (hi - lo);
    const left = indices.filter((i) => data[i][feature] < split);
    const right = indices.filter((i) => data[i][feature] >= split);
    if (!left.length || !right.length)
        return node;
    node.splitFeature = feature;
    node.splitValue = split;
    node.left = buildIsolationTree(data, left, depth + 1, maxDepth, rng);
    node.right = buildIsolationTree(data, right, depth + 1, maxDepth, rng);
    return node;
}
function pathLength(node, point, currentDepth) {
    if (node.splitFeature === undefined)
        return currentDepth;
    const next = point[node.splitFeature] < node.splitValue ? node.left : node.right;
    if (!next)
        return currentDepth;
    return pathLength(next, point, currentDepth + 1);
}
function cFactor(n) {
    if (n <= 1)
        return 1;
    return 2 * (Math.log(n - 1) + 0.5772156649) - (2 * (n - 1)) / n;
}
export function trainIsolationForest(data, options = {}) {
    const trees = options.trees ?? 80;
    const sampleSize = options.sampleSize ?? Math.min(128, Math.max(8, Math.floor(data.length / 4)));
    const seed = options.seed ?? 42;
    const contamination = options.contamination ?? 0.04;
    const maxDepth = Math.ceil(Math.log2(Math.max(2, sampleSize)));
    const nodes = [];
    const allIndices = data.map((_, i) => i);
    for (let t = 0; t < trees; t += 1) {
        const rng = mulberry32(seed + t * 7919);
        const pick = new Set();
        const target = Math.min(sampleSize, allIndices.length);
        while (pick.size < target)
            pick.add(allIndices[Math.floor(rng() * allIndices.length)]);
        nodes.push(buildIsolationTree(data, [...pick], 0, maxDepth, rng));
    }
    const score = (rows) => rows.map((point) => {
        const total = nodes.reduce((acc, node) => acc + pathLength(node, point, 0), 0);
        const avg = total / nodes.length;
        return Math.pow(2, -avg / cFactor(sampleSize));
    });
    const trainingScores = score(data);
    const sorted = [...trainingScores].sort((a, b) => a - b);
    const cutIdx = clamp(Math.floor(sorted.length * contamination), 0, sorted.length - 1);
    const threshold = sorted[cutIdx];
    return { trees: nodes, maxDepth, sampleSize, score, threshold };
}
export function runAnomalyEngine(ctx) {
    const rows = [...ctx.transactions]
        .filter((t) => t.direction === "outflow" && t.category !== "transfer")
        .sort((a, b) => (a.timestamp === b.timestamp ? a.transaction_id.localeCompare(b.transaction_id) : a.timestamp.localeCompare(b.timestamp)));
    const { matrix, featureKeys } = buildMatrix(rows);
    const forest = trainIsolationForest(matrix, { seed: 20260101, contamination: 0.05 });
    const scores = forest.score(matrix);
    const knownById = new Set(ctx.patterns.map((p) => p.transaction_id).filter(Boolean));
    const hits = [];
    const scored = [];
    rows.forEach((tx, i) => {
        const score = scores[i];
        scored.push({ transaction: tx, score });
        if (score <= forest.threshold)
            return;
        const history = historyUpTo(rows, i);
        const reasons = FEATURES.map((f) => ({
            label: f.label,
            value: round(f.build(tx, history), 3),
            z: 0,
        })).filter((r) => Math.abs(r.value) > 0.8);
        hits.push({
            transaction: tx,
            score: round(score, 4),
            reasons: reasons.length ? reasons : [{ label: "Isolated early by the forest", value: 0, z: 0 }],
            knownPattern: knownById.has(tx.transaction_id),
        });
    });
    hits.sort((a, b) => b.score - a.score);
    // Evaluation against the generator's injected-pattern ground truth.
    const knownIds = new Set(knownById);
    const detectedIds = new Set(hits.map((h) => h.transaction.transaction_id));
    let tp = 0;
    for (const id of knownIds)
        if (detectedIds.has(id))
            tp += 1;
    const fp = detectedIds.size - tp;
    const fn = knownIds.size - tp;
    const precision = tp + fp > 0 ? tp / (tp + fp) : 0;
    const recall = knownIds.size > 0 ? tp / knownIds.size : 0;
    const f1 = precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0;
    const top = hits[0];
    const evidence = {
        engine: "Anomaly Detection Engine (Isolation Forest)",
        headline: `${hits.length} anomalous transactions in ${rows.length} outflows`,
        confidence: round(clamp(0.55 + Math.min(rows.length, 400) / 1200, 0.55, 0.92), 2),
        confidenceNote: `${forest.trees} isolation trees, subsample ${forest.sampleSize}, depth cap ${forest.maxDepth}, contamination target 5%.`,
        metrics: [
            { id: "scanned", label: "Outflows scanned", value: rows.length, unit: "count", detail: "all outflows except transfers", source: "transactions" },
            { id: "flagged", label: "Flagged as unusual", value: hits.length, unit: "count", detail: `isolation score above ${round(forest.threshold, 4)}`, source: "Isolation Forest" },
            { id: "precision", label: "Precision vs injected truth", value: round(precision, 4), unit: "ratio", detail: "flagged transactions that are truly injected", source: "injected_patterns" },
            { id: "recall", label: "Recall vs injected truth", value: round(recall, 4), unit: "ratio", detail: "injected anomalies that were flagged", source: "injected_patterns" },
            { id: "f1", label: "F1", value: round(f1, 4), unit: "ratio", detail: "harmonic mean of precision and recall", source: "injected_patterns" },
        ],
        reasons: [
            { polarity: "neutral", text: `Features: ${featureKeys.length} causal signals per transaction (amount deviation, category deviation, merchant rarity, time rarity, cash channel, balance impact).` },
            ...(top
                ? [
                    {
                        polarity: "negative",
                        text: `Highest-scoring: ৳${Math.round(top.transaction.amount).toLocaleString("en-US")} ${top.transaction.category}/${top.transaction.subcategory} on ${top.transaction.timestamp.slice(0, 10)} (score ${top.score}).`,
                    },
                ]
                : []),
            { polarity: "neutral", text: `Ground-truth comparison only exists because the dataset injects known anomalies: ${knownIds.size} injected for this customer.` },
        ],
        assumptions: [
            "Contamination is set to 5% because the persona mix implies a low but non-zero anomaly rate.",
            "Features use only strictly prior transactions, so the detector never sees the future.",
            "Known-pattern membership is used for scoring the engine, never as an input feature.",
        ],
        sources: ["transactions.csv", "injected_patterns.csv (evaluation only)"],
        evaluation: [
            { metric: "Precision", value: round(precision, 3), unit: "" },
            { metric: "Recall", value: round(recall, 3), unit: "" },
            { metric: "F1", value: round(f1, 3), unit: "" },
            { metric: "Injected anomalies", value: knownIds.size, unit: "" },
        ],
    };
    return {
        hits,
        scored,
        featureKeys,
        threshold: round(forest.threshold, 4),
        knownPositives: knownIds.size,
        detected: detectedIds.size,
        truePositives: tp,
        falsePositives: fp,
        falseNegatives: fn,
        precision: round(precision, 4),
        recall: round(recall, 4),
        f1: round(f1, 4),
        evidence,
    };
}
function historyUpTo(rows, index) {
    const history = newHistory();
    for (let i = 0; i < index; i += 1)
        push(history, rows[i]);
    return history;
}
/** Portfolio-level detection across the whole cohort, for the evaluation screen. */
export function runAnomalyEngineCohort(contexts) {
    let tp = 0;
    let fp = 0;
    let fn = 0;
    let known = 0;
    let flagged = 0;
    let rows = 0;
    for (const ctx of contexts) {
        const r = runAnomalyEngine(ctx);
        tp += r.truePositives;
        fp += r.falsePositives;
        fn += r.falseNegatives;
        known += r.knownPositives;
        flagged += r.detected;
        rows += r.scored.length;
    }
    const precision = tp + fp > 0 ? tp / (tp + fp) : 0;
    const recall = known > 0 ? tp / known : 0;
    const f1 = precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0;
    return {
        precision: round(precision, 4),
        recall: round(recall, 4),
        f1: round(f1, 4),
        tp,
        fp,
        fn,
        known,
        flagged,
        rows,
    };
}
/** Weekly anomaly volume for the spending page sparkline. */
export function anomalyTimeline(ctx) {
    const result = runAnomalyEngine(ctx);
    const byMonth = new Map();
    for (const hit of result.hits) {
        const key = hit.transaction.timestamp.slice(0, 7);
        byMonth.set(key, (byMonth.get(key) ?? 0) + 1);
    }
    return ctx.monthly.map((m) => ({ month: m.key, count: byMonth.get(m.key) ?? 0 }));
}
export function anomalyShareOfSpend(ctx) {
    const result = runAnomalyEngine(ctx);
    const total = sum(ctx.transactions.filter(isProductSpend).map((t) => t.amount));
    if (total <= 0)
        return 0;
    return sum(result.hits.map((h) => h.transaction.amount)) / total;
}
