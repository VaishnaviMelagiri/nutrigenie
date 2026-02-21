/**
 * Personalized Meal Plan Generator by IOM Bioworks
 */

// ═══ Config ═══
const API_URL = 'https://f8c7x5y2hg.execute-api.us-east-1.amazonaws.com/prod';

const $ = id => document.getElementById(id);

let currentDay = 'day_1';
let mealPlanData = null;
let swapTarget = null; // {day, meal_type, name}

document.addEventListener('DOMContentLoaded', () => {
    $('generateBtn').addEventListener('click', handleGenerate);
    $('kitId').addEventListener('keypress', (e) => { if (e.key === 'Enter') handleGenerate(); });
});

// ═══ Main Flow ═══
async function handleGenerate() {
    const kitId = $('kitId').value.trim();
    if (!kitId) { showToast('Please enter a Kit ID', 'error'); return; }

    setLoading(true);
    setStatus('processing', 'Generating...');

    try {
        showToast('📋 Loading patient data...', 'info', 3000);
        const profile = await apiCall(`/patient/${kitId}`, 'GET');
        renderProfile(profile);

        showToast('🧠 AI is generating your meal plan (30-60s)...', 'info', 10000);
        const result = await apiCall('/meal', 'POST', { kit_id: kitId });

        mealPlanData = result.meal_plan;
        currentDay = 'day_1';
        renderMealPlan(result);

        setStatus('online', 'Ready');
        showToast('✅ Meal plan generated! Click 🔄 Swap on any meal to replace it.', 'success', 5000);

    } catch (err) {
        console.error(err);
        showToast(`❌ ${err.message}`, 'error', 6000);
        setStatus('error', 'Error');
    } finally {
        setLoading(false);
    }
}

// ═══ Render Profile ═══
function renderProfile(profile) {
    $('profileSection').classList.remove('hidden');

    const cards = [
        { label: 'Kit ID', value: profile.kit_id },
        { label: 'Diet', value: profile.diet_type || 'Veg' },
        { label: 'BMI', value: profile.bmi || 'N/A' },
        { label: 'IBS Type', value: profile.ibs_info?.subtype || 'N/A' },
        { label: 'Severity', value: profile.ibs_info?.severity_level || 'N/A' },
        { label: 'Location', value: profile.location || 'N/A' },
        { label: 'Gender', value: profile.gender || 'N/A' },
        { label: 'Age', value: profile.age || 'N/A' },
    ];

    let html = cards.map(c => `
        <div class="profile-card">
            <div class="profile-card-label">${c.label}</div>
            <div class="profile-card-value">${esc(String(c.value))}</div>
        </div>
    `).join('');

    if (profile.avoid_list?.length) {
        html += `<div class="profile-card" style="grid-column: span 2">
            <div class="profile-card-label">🚫 Avoid List (Food Allergies)</div>
            <div class="profile-card-value">${profile.avoid_list.map(a => `<span class="avoid-tag red">${esc(a)}</span>`).join('')}</div>
        </div>`;
    }

    const bInc = profile.bacteria_to_increase?.filter(b => !b.name.includes('Other')).slice(0, 5) || [];
    const bDec = profile.bacteria_to_decrease?.filter(b => !b.name.includes('Other')).slice(0, 5) || [];
    if (bInc.length) {
        html += `<div class="profile-card" style="grid-column: span 2">
            <div class="profile-card-label">📈 Bacteria to Increase</div>
            <div class="profile-card-value">${bInc.map(b => `<span class="avoid-tag green">${esc(b.name)}</span>`).join('')}</div>
        </div>`;
    }
    if (bDec.length) {
        html += `<div class="profile-card" style="grid-column: span 2">
            <div class="profile-card-label">📉 Bacteria to Decrease</div>
            <div class="profile-card-value">${bDec.map(b => `<span class="avoid-tag blue">${esc(b.name)}</span>`).join('')}</div>
        </div>`;
    }

    $('profileGrid').innerHTML = html;
    $('profileSection').scrollIntoView({ behavior: 'smooth' });
}

// ═══ Render Meal Plan ═══
function renderMealPlan(result) {
    $('mealSection').classList.remove('hidden');
    $('planInfo').textContent = `Kit: ${result.kit_id} • Generated: ${new Date(result.generated_at).toLocaleString()} • Diet: ${result.patient_summary?.diet_type || 'Veg'}`;

    renderDayTabs();
    renderDay('day_1');
    $('mealSection').scrollIntoView({ behavior: 'smooth' });
}

function renderDayTabs() {
    const names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    $('dayTabs').innerHTML = names.map((n, i) => {
        const key = `day_${i + 1}`;
        return `<button class="day-tab ${key === currentDay ? 'active' : ''}" onclick="switchDay('${key}')">${n}</button>`;
    }).join('');
}

function switchDay(day) {
    currentDay = day;
    document.querySelectorAll('.day-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.day-tab').forEach(t => {
        if (t.textContent === ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][parseInt(day.split('_')[1]) - 1]) t.classList.add('active');
    });
    renderDay(day);
}

function renderDay(dayKey) {
    const day = mealPlanData?.[dayKey];
    if (!day) { $('mealsContainer').innerHTML = '<p style="text-align:center;color:var(--text-muted)">No data for this day</p>'; return; }

    const meals = ['breakfast', 'mid_morning_snack', 'lunch', 'evening_snack', 'dinner'];
    const labels = { breakfast: '🌅 Breakfast', mid_morning_snack: '🍎 Snack', lunch: '☀️ Lunch', evening_snack: '🫖 Tea Time', dinner: '🌙 Dinner' };

    let html = '';
    let totals = { cal: 0, pro: 0, carb: 0, fat: 0, fib: 0 };

    meals.forEach(type => {
        const m = day[type];
        if (!m || typeof m !== 'object') return;

        const cal = m.total_calories || 0;
        const pro = m.protein_g || 0;
        const carb = m.carbs_g || 0;
        const fat = m.fat_g || 0;
        const fib = m.fiber_g || 0;
        totals.cal += cal; totals.pro += pro; totals.carb += carb; totals.fat += fat; totals.fib += fib;

        const ings = (m.ingredients || []).map(i => {
            let nutInfo = '';
            if (i.nutrition_per_serving) {
                nutInfo = ` (${i.nutrition_per_serving.calories} kcal, ${i.nutrition_per_serving.protein_g}g pro)`;
            }
            return `<div class="ingredient-row">
                <span class="ingredient-name">${esc(i.name || '')}</span>
                <span class="ingredient-qty">${i.quantity_g || ''}g${nutInfo ? `<br><span class="ingredient-nutrition">${nutInfo}</span>` : ''}</span>
            </div>`;
        }).join('');

        html += `<div class="meal-card" id="meal-${dayKey}-${type}">
            <div class="meal-content">
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                    <span class="meal-type">${labels[type] || type}</span>
                    ${m.prep_time_min ? `<span style="font-size:0.7rem;color:var(--text-muted)">⏱ ${m.prep_time_min}min</span>` : ''}
                </div>
                <h3 class="meal-name">${esc(m.name || 'Meal')}</h3>
                ${m.benefits ? `<p class="meal-benefits">${esc(m.benefits)}</p>` : ''}
                <div class="ingredients-list">
                    <div class="ingredients-label">Ingredients</div>
                    ${ings}
                </div>
                <div class="macro-grid">
                    <div class="macro-box"><span class="macro-val">${pro}g</span><span class="macro-lbl">Protein</span></div>
                    <div class="macro-box"><span class="macro-val">${carb}g</span><span class="macro-lbl">Carbs</span></div>
                    <div class="macro-box"><span class="macro-val">${fat}g</span><span class="macro-lbl">Fat</span></div>
                    <div class="macro-box"><span class="macro-val">${fib}g</span><span class="macro-lbl">Fiber</span></div>
                </div>
                <button class="btn-swap-meal" onclick="openSwapModal('${dayKey}', '${type}', '${esc(m.name || 'Meal')}')">
                    🔄 Swap This Meal
                </button>
            </div>
            <div class="meal-cal-box">
                <span class="cal-value">${cal}</span>
                <span class="cal-label">kcal</span>
            </div>
        </div>`;
    });

    $('mealsContainer').innerHTML = html;

    // Daily summary
    const target = mealPlanData.calorie_target || 2000;
    const summary = $('dailySummary');
    summary.classList.remove('hidden');
    summary.innerHTML = `
        <div class="summary-title">📊 Daily Totals — ${dayKey.replace('_', ' ').replace('d', 'D')}</div>
        <div class="bar-grid">
            ${makeBar('Calories', totals.cal, target, 'kcal', 'cal')}
            ${makeBar('Protein', totals.pro, 50, 'g', 'pro')}
            ${makeBar('Carbs', totals.carb, 300, 'g', 'carb')}
            ${makeBar('Fat', totals.fat, 65, 'g', 'fat')}
            ${makeBar('Fiber', totals.fib, 25, 'g', 'fib')}
        </div>
    `;
}

function makeBar(label, val, max, unit, cls) {
    const pct = Math.min(100, (val / max) * 100);
    return `<div class="bar-item">
        <div class="bar-header"><span class="bar-label">${label}</span><span class="bar-value">${Math.round(val)}/${max} ${unit}</span></div>
        <div class="bar-track"><div class="bar-fill ${cls}" style="width:${pct}%"></div></div>
    </div>`;
}

// ═══ Swap Feature ═══
function openSwapModal(day, mealType, mealName) {
    swapTarget = { day, meal_type: mealType, name: mealName };
    const labels = { breakfast: 'Breakfast', mid_morning_snack: 'Mid-Morning Snack', lunch: 'Lunch', evening_snack: 'Evening Snack', dinner: 'Dinner' };
    $('swapMealInfo').innerHTML = `Replacing <strong>${esc(mealName)}</strong> (${labels[mealType] || mealType}, ${day.replace('_', ' ')})`;
    $('swapReason').value = '';
    $('swapModal').classList.remove('hidden');
}

function closeSwapModal() {
    $('swapModal').classList.add('hidden');
    swapTarget = null;
}

async function confirmSwap() {
    if (!swapTarget) return;

    const kitId = $('kitId').value.trim();
    const reason = $('swapReason').value.trim();
    const { day, meal_type, name } = swapTarget;

    // Show loading
    $('swapBtnText').textContent = 'Swapping...';
    $('swapSpinner').classList.remove('hidden');
    const btn = $('swapBtn');
    btn.disabled = true;

    // Highlight the card being swapped
    const card = document.getElementById(`meal-${day}-${meal_type}`);
    if (card) card.classList.add('swapping');

    try {
        const result = await apiCall('/swap', 'POST', {
            kit_id: kitId,
            day: day,
            meal_type: meal_type,
            current_meal: name,
            reason: reason,
        });

        // Update the meal plan data in memory
        if (result.new_meal && mealPlanData[day]) {
            mealPlanData[day][meal_type] = result.new_meal;
            renderDay(day); // Re-render current day
            showToast(`✅ Swapped! "${name}" → "${result.new_meal.name}"`, 'success', 5000);

            // Flash animation on the new card
            setTimeout(() => {
                const newCard = document.getElementById(`meal-${day}-${meal_type}`);
                if (newCard) newCard.classList.add('swapped');
            }, 50);
        }

        closeSwapModal();

    } catch (err) {
        showToast(`❌ Swap failed: ${err.message}`, 'error', 5000);
        if (card) card.classList.remove('swapping');
    } finally {
        $('swapBtnText').textContent = '🔄 Get Alternative';
        $('swapSpinner').classList.add('hidden');
        btn.disabled = false;
    }
}

// ═══ API ═══
async function apiCall(endpoint, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body && method !== 'GET') opts.body = JSON.stringify(body);
    const res = await fetch(`${API_URL}${endpoint}`, opts);
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.error || `HTTP ${res.status}`); }
    return res.json();
}

// ═══ Helpers ═══
function setLoading(on) {
    $('generateBtn').disabled = on;
    $('btnText').classList.toggle('hidden', on);
    $('spinner').classList.toggle('hidden', !on);
}
function setStatus(type, text) {
    document.querySelector('.status-dot').className = `status-dot ${type}`;
    document.querySelector('.status-text').textContent = text;
}
function esc(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
function showToast(msg, type = 'info', dur = 4000) {
    const t = document.createElement('div'); t.className = `toast ${type}`; t.textContent = msg;
    $('toastContainer').appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(40px)'; t.style.transition = 'all 0.3s'; setTimeout(() => t.remove(), 300); }, dur);
}
