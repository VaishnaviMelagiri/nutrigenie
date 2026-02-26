/**
 * Personalized Meal Plan Generator by IOM Bioworks
 */

// ═══ Config ═══
const API_URL = 'https://f8c7x5y2hg.execute-api.us-east-1.amazonaws.com/prod';

const $ = id => document.getElementById(id);

let currentDay = 'day_1';
let mealPlanData = null;
let swapTarget = null;
let patientProfile = null;

// ═══ Ingredient → Dishes Map (yes-list driven, variety per meal type) ═══
// Each yes-list ingredient maps to multiple dishes per meal time
// so the user sees different preparations of the same beneficial ingredient
const INGREDIENT_DISH_MAP = {
    // OATS — Faecalibacterium, gut fibre
    'oats': {
        label: 'Oats (Gut Fibre)',
        breakfast: [
            { name: 'Oats Porridge with Banana & Jaggery', ings: 'Rolled oats, banana, jaggery, cinnamon, milk', cal: 280, pro: 8, carb: 48, fat: 5 },
            { name: 'Oats Upma', ings: 'Rolled oats, onion, mustard seeds, curry leaves, green chilli', cal: 230, pro: 7, carb: 38, fat: 6 },
            { name: 'Oats Idli', ings: 'Oats, curd, eno, ginger, coriander', cal: 210, pro: 8, carb: 34, fat: 4 },
        ],
        snack: [
            { name: 'Banana Oats Smoothie', ings: 'Banana, oats, honey, curd, cardamom', cal: 220, pro: 6, carb: 40, fat: 4 },
            { name: 'Oats Energy Bar', ings: 'Oats, jaggery, peanuts, sesame seeds, ghee', cal: 250, pro: 7, carb: 36, fat: 9 },
        ],
        dinner: [
            { name: 'Oats Khichdi', ings: 'Oats, moong dal, ghee, cumin, turmeric, vegetables', cal: 310, pro: 12, carb: 48, fat: 7 },
            { name: 'Oats Vegetable Soup', ings: 'Oats, carrot, beans, garlic, pepper, broth', cal: 180, pro: 6, carb: 28, fat: 4 },
        ],
    },
    // RAGI (Finger Millet) — Faecalibacterium, calcium
    'ragi': {
        label: 'Ragi / Finger Millet',
        breakfast: [
            { name: 'Ragi Dosa with Coconut Chutney', ings: 'Ragi flour, rice flour, onion, cumin, coconut chutney', cal: 220, pro: 6, carb: 38, fat: 4 },
            { name: 'Ragi Porridge (Ambil)', ings: 'Ragi flour, buttermilk, salt, cumin', cal: 180, pro: 5, carb: 34, fat: 2 },
            { name: 'Ragi Idli', ings: 'Ragi, urad dal, rice, salt', cal: 200, pro: 7, carb: 36, fat: 2 },
        ],
        snack: [
            { name: 'Ragi Ladoo', ings: 'Roasted ragi, jaggery, ghee, cardamom', cal: 210, pro: 4, carb: 34, fat: 8 },
            { name: 'Ragi Malt with Jaggery', ings: 'Ragi flour, milk, jaggery, cardamom', cal: 190, pro: 7, carb: 30, fat: 4 },
        ],
        lunch: [
            { name: 'Ragi Roti with Dal', ings: 'Ragi flour, water, toor dal, ghee, curry leaves', cal: 320, pro: 11, carb: 50, fat: 6 },
        ],
        dinner: [
            { name: 'Ragi Mudde with Sambhar', ings: 'Ragi flour ball, mixed vegetable sambhar', cal: 300, pro: 10, carb: 52, fat: 4 },
            { name: 'Ragi Chapati with Sabzi', ings: 'Ragi flour, wheat flour, ghee, seasonal vegetable', cal: 280, pro: 8, carb: 44, fat: 7 },
        ],
    },
    // WHOLE WHEAT — Faecalibacterium, dietary fibre
    'whole wheat': {
        label: 'Whole Wheat',
        breakfast: [
            { name: 'Whole Wheat Paratha with Curd', ings: 'Whole wheat flour, ghee, fresh curd', cal: 300, pro: 9, carb: 40, fat: 10 },
            { name: 'Wheat Dalia Porridge', ings: 'Broken wheat, milk, jaggery, cardamom, nuts', cal: 260, pro: 8, carb: 42, fat: 6 },
            { name: 'Wheat Rava Upma', ings: 'Wheat rava, mustard, curry leaves, vegetables', cal: 230, pro: 6, carb: 38, fat: 5 },
        ],
        lunch: [
            { name: 'Whole Wheat Roti with Palak Dal', ings: 'Whole wheat roti, moong dal, spinach, ghee', cal: 350, pro: 14, carb: 48, fat: 8 },
            { name: 'Wheat Pulao', ings: 'Broken wheat, mixed vegetables, biryani masala', cal: 310, pro: 9, carb: 50, fat: 6 },
            { name: 'Chapati with Rajma', ings: 'Wheat chapati, kidney beans, onion, tomato', cal: 370, pro: 14, carb: 52, fat: 7 },
        ],
        snack: [
            { name: 'Wheat Toast with Peanut Butter', ings: 'Whole wheat bread, homemade peanut butter', cal: 200, pro: 8, carb: 24, fat: 9 },
        ],
        dinner: [
            { name: 'Wheat Dalia Khichdi', ings: 'Broken wheat, moong dal, vegetables, ghee, cumin', cal: 280, pro: 10, carb: 44, fat: 6 },
            { name: 'Pumpkin Soup with Wheat Toast', ings: 'Pumpkin, onion, garlic, wheat toast', cal: 210, pro: 5, carb: 34, fat: 5 },
        ],
    },
    // MOONG DAL — Bifidobacterium, protein
    'moong': {
        label: 'Moong Dal (Protein)',
        breakfast: [
            { name: 'Moong Dal Cheela', ings: 'Moong dal batter, onion, green chilli, coriander, ginger', cal: 200, pro: 12, carb: 28, fat: 4 },
            { name: 'Pesarattu (Green Gram Dosa)', ings: 'Whole green moong, rice, ginger, cumin, onion', cal: 210, pro: 10, carb: 32, fat: 4 },
        ],
        snack: [
            { name: 'Moong Sprouts Chaat', ings: 'Moong sprouts, onion, tomato, lemon, chaat masala', cal: 150, pro: 10, carb: 22, fat: 2 },
            { name: 'Moong Dal Soup', ings: 'Moong dal, garlic, ginger, cumin, lemon', cal: 160, pro: 10, carb: 20, fat: 3 },
        ],
        lunch: [
            { name: 'Moong Dal with Brown Rice', ings: 'Moong dal, brown rice, ghee, garlic, turmeric', cal: 350, pro: 14, carb: 54, fat: 7 },
            { name: 'Moong Dal Khichdi', ings: 'Moong dal, rice, ghee, cumin, turmeric, vegetables', cal: 320, pro: 12, carb: 50, fat: 6 },
        ],
        dinner: [
            { name: 'Moong Dal Khichdi with Ghee', ings: 'Rice, moong dal, ghee, turmeric, cumin, vegetables', cal: 320, pro: 12, carb: 50, fat: 7 },
            { name: 'Moong Dal Halwa (light)', ings: 'Moong dal, jaggery, ghee, cardamom', cal: 250, pro: 8, carb: 36, fat: 9 },
        ],
    },
    // FLAXSEED — Faecalibacterium, omega-3
    'flaxseed': {
        label: 'Flaxseed (Omega-3)',
        breakfast: [
            { name: 'Flaxseed Banana Smoothie', ings: 'Banana, flaxseed powder, curd, honey', cal: 220, pro: 7, carb: 36, fat: 6 },
            { name: 'Flaxseed Chilla', ings: 'Wheat flour, flaxseed, onion, green chilli', cal: 210, pro: 8, carb: 30, fat: 6 },
        ],
        snack: [
            { name: 'Flaxseed Raita', ings: 'Curd, flaxseed powder, cumin, salt, mint', cal: 120, pro: 6, carb: 8, fat: 6 },
            { name: 'Flaxseed Ladoo', ings: 'Roasted flaxseed, jaggery, sesame, ghee', cal: 200, pro: 5, carb: 22, fat: 11 },
        ],
        lunch: [
            { name: 'Flaxseed Roti with Dal', ings: 'Wheat + flaxseed flour roti, toor dal, ghee', cal: 340, pro: 12, carb: 48, fat: 9 },
        ],
        dinner: [
            { name: 'Flaxseed Vegetable Curry', ings: 'Mixed vegetables, flaxseed powder, onion, tomato', cal: 240, pro: 8, carb: 30, fat: 9 },
        ],
    },
    // CURD / FERMENTED FOODS — Bifidobacterium, Lactobacillus
    'curd': {
        label: 'Curd / Fermented Foods',
        breakfast: [
            { name: 'Curd with Poha', ings: 'Pressed rice, curd, mustard, curry leaves, pomegranate', cal: 260, pro: 8, carb: 42, fat: 5 },
            { name: 'Lassi with Oats', ings: 'Curd, oats, honey, cardamom', cal: 220, pro: 8, carb: 34, fat: 5 },
        ],
        snack: [
            { name: 'Buttermilk (Chaas)', ings: 'Curd, water, cumin, mint, salt', cal: 60, pro: 3, carb: 5, fat: 2 },
            { name: 'Sweet Lassi', ings: 'Curd, sugar, cardamom, rose water', cal: 150, pro: 5, carb: 22, fat: 4 },
            { name: 'Dahi Vada', ings: 'Urad dal vada, curd, tamarind, cumin', cal: 220, pro: 8, carb: 28, fat: 8 },
        ],
        lunch: [
            { name: 'Curd Rice with Pickle', ings: 'Cooked rice, fresh curd, pomegranate, mustard', cal: 280, pro: 8, carb: 45, fat: 6 },
            { name: 'Curd Pulao', ings: 'Rice, curd, mint, vegetables, cumin', cal: 300, pro: 9, carb: 48, fat: 6 },
        ],
        dinner: [
            { name: 'Fermented Rice with Pickle', ings: 'Leftover rice, water, curd, mango pickle', cal: 220, pro: 5, carb: 42, fat: 3 },
            { name: 'Chapati with Curd Curry', ings: 'Wheat chapati, curd gravy, besan, cumin', cal: 310, pro: 10, carb: 44, fat: 8 },
        ],
    },
    // RAJMA / KIDNEY BEANS — Anaerostipes
    'rajma': {
        label: 'Rajma / Kidney Beans',
        lunch: [
            { name: 'Rajma Chawal', ings: 'Kidney beans, rice, onion, tomato, garam masala', cal: 400, pro: 15, carb: 60, fat: 7 },
            { name: 'Rajma Roti', ings: 'Kidney beans, wheat roti, onion, spices', cal: 360, pro: 14, carb: 52, fat: 7 },
        ],
        snack: [
            { name: 'Rajma Soup', ings: 'Kidney beans, onion, garlic, tomato, pepper', cal: 180, pro: 10, carb: 24, fat: 4 },
        ],
        dinner: [
            { name: 'Chole with Kulcha', ings: 'Chickpeas, onion, tomato, wheat kulcha', cal: 400, pro: 14, carb: 56, fat: 10 },
        ],
    },
    // BAJRA (Pearl Millet) — Dialister
    'bajra': {
        label: 'Bajra / Pearl Millet',
        breakfast: [
            { name: 'Bajra Roti with Jaggery & Ghee', ings: 'Bajra flour, jaggery, ghee', cal: 260, pro: 6, carb: 42, fat: 8 },
            { name: 'Bajra Porridge', ings: 'Bajra flour, milk, jaggery, cardamom', cal: 240, pro: 7, carb: 38, fat: 6 },
        ],
        lunch: [
            { name: 'Bajra Khichdi', ings: 'Bajra, moong dal, ghee, cumin, turmeric', cal: 320, pro: 11, carb: 48, fat: 7 },
            { name: 'Bajra Roti with Brinjal Bharta', ings: 'Bajra roti, roasted brinjal, onion, garlic', cal: 300, pro: 8, carb: 46, fat: 7 },
        ],
        dinner: [
            { name: 'Bajra Roti with Mixed Veg Curry', ings: 'Bajra roti, seasonal vegetables, spices', cal: 300, pro: 8, carb: 46, fat: 7 },
        ],
    },
    // BANANA — Anaerostipes, prebiotic
    'banana': {
        label: 'Banana (Prebiotic)',
        breakfast: [
            { name: 'Banana Pancake', ings: 'Ripe banana, oats flour, cinnamon, honey', cal: 240, pro: 6, carb: 44, fat: 4 },
            { name: 'Banana Smoothie Bowl', ings: 'Banana, curd, honey, flaxseed, fruits', cal: 260, pro: 8, carb: 42, fat: 5 },
        ],
        snack: [
            { name: 'Banana with Peanut Butter', ings: 'Ripe banana, homemade peanut butter', cal: 200, pro: 6, carb: 30, fat: 8 },
            { name: 'Banana Stem Juice', ings: 'Banana stem, lemon, ginger, salt', cal: 40, pro: 1, carb: 8, fat: 0 },
        ],
        lunch: [
            { name: 'Raw Banana Curry with Rice', ings: 'Raw banana, coconut, mustard, rice', cal: 320, pro: 7, carb: 55, fat: 6 },
        ],
        dinner: [
            { name: 'Banana Stem Sabzi', ings: 'Banana stem, coconut, mustard seeds, curry leaves', cal: 130, pro: 3, carb: 20, fat: 5 },
        ],
    },
    // DEFAULT (when patient data has no specific match)
    '_default': {
        label: 'Gut Health Classics',
        breakfast: [
            { name: 'Idli with Sambhar', ings: 'Rice idli, toor dal sambhar, vegetables', cal: 230, pro: 8, carb: 42, fat: 3 },
            { name: 'Poha with Peanuts', ings: 'Pressed rice, peanuts, turmeric, curry leaves, lemon', cal: 250, pro: 7, carb: 38, fat: 8 },
        ],
        snack: [
            { name: 'Roasted Chana', ings: 'Roasted chickpeas, lemon, chaat masala', cal: 160, pro: 9, carb: 24, fat: 4 },
            { name: 'Fruit Chaat', ings: 'Apple, guava, pomegranate, chaat masala, lemon', cal: 120, pro: 2, carb: 28, fat: 1 },
        ],
        lunch: [
            { name: 'Dal Tadka with Brown Rice', ings: 'Toor dal, garlic, cumin, ghee, brown rice', cal: 380, pro: 14, carb: 58, fat: 8 },
            { name: 'Sambhar Rice', ings: 'Rice, mixed veg sambhar, coconut chutney', cal: 340, pro: 10, carb: 54, fat: 6 },
        ],
        dinner: [
            { name: 'Moong Dal Khichdi', ings: 'Rice, moong dal, ghee, turmeric, cumin', cal: 320, pro: 12, carb: 50, fat: 7 },
            { name: 'Masoor Dal with Chapati', ings: 'Masoor dal, wheat chapati, ghee, lemon', cal: 340, pro: 13, carb: 50, fat: 7 },
        ],
    }
};

// Keywords from the patient's report that map to our ingredient keys
const INGREDIENT_KEYWORDS = [
    { keys: ['oat', 'oats', 'rolled oat'], mapTo: 'oats' },
    { keys: ['ragi', 'finger millet', 'nachni'], mapTo: 'ragi' },
    { keys: ['whole wheat', 'wheat', 'atta', 'chapati', 'roti'], mapTo: 'whole wheat' },
    { keys: ['moong', 'green gram', 'mung'], mapTo: 'moong' },
    { keys: ['flaxseed', 'flax seed', 'linseed', 'alsi'], mapTo: 'flaxseed' },
    { keys: ['curd', 'dahi', 'yogurt', 'fermented', 'probiotic'], mapTo: 'curd' },
    { keys: ['rajma', 'kidney bean'], mapTo: 'rajma' },
    { keys: ['bajra', 'pearl millet'], mapTo: 'bajra' },
    { keys: ['banana', 'kela'], mapTo: 'banana' },
];

// Bacteria name → which ingredients to suggest (based on which bacteria each food supports)
const BACTERIA_TO_INGREDIENTS = {
    'Faecalibacterium': ['oats', 'ragi', 'whole wheat', 'flaxseed', 'banana'],
    'Faecalibacterium prausnitzii': ['oats', 'ragi', 'whole wheat', 'flaxseed'],
    'Bifidobacterium': ['curd', 'moong', 'oats', 'banana'],
    'Lactobacillus': ['curd', 'flaxseed', 'moong'],
    'Bacteroides': ['moong', 'whole wheat', 'curd', 'bajra'],
    'Dialister': ['bajra', 'ragi', 'whole wheat'],
    'Anaerostipes': ['banana', 'rajma', 'oats'],
    'Roseburia': ['oats', 'whole wheat', 'ragi'],
    'Akkermansia': ['curd', 'flaxseed', 'oats'],
    'Ruminococcus': ['oats', 'whole wheat', 'ragi'],
    'Blautia': ['curd', 'moong', 'bajra'],
    'Prevotella': ['whole wheat', 'ragi', 'bajra'],
};

// Bacteria to REDUCE → ingredients that do NOT make things worse (we still show good foods)
const BACTERIA_TO_REDUCE_AVOID = {
    'Clostridium': ['rajma'],  // avoid high fermentable foods if trying to reduce
};

// Build ingredient list from patient profile (bacteria to increase drives which foods to show)
function getPatientIngredientKeys() {
    const ingSet = new Set();

    if (patientProfile) {
        const toIncrease = patientProfile.bacteria_to_increase || [];
        toIncrease.forEach(b => {
            const bName = b.name || '';
            // Try exact match first
            const exact = BACTERIA_TO_INGREDIENTS[bName];
            if (exact) { exact.forEach(i => ingSet.add(i)); return; }
            // Try partial match
            Object.keys(BACTERIA_TO_INGREDIENTS).forEach(key => {
                if (bName.toLowerCase().includes(key.toLowerCase()) || key.toLowerCase().includes(bName.toLowerCase())) {
                    BACTERIA_TO_INGREDIENTS[key].forEach(i => ingSet.add(i));
                }
            });
        });

        // Also scan prebiotics text for keyword matches
        const prebioticText = (patientProfile.prebiotics || '').toLowerCase();
        INGREDIENT_KEYWORDS.forEach(({ keys, mapTo }) => {
            if (keys.some(k => prebioticText.includes(k))) ingSet.add(mapTo);
        });
    }

    // Fallback if nothing matched
    if (ingSet.size === 0) {
        ['oats', 'moong', 'curd', 'ragi', 'whole wheat', 'bajra', 'banana', 'flaxseed'].forEach(i => ingSet.add(i));
    }
    return Array.from(ingSet);
}

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
        patientProfile = profile; // store globally for yes-list
        renderProfile(profile);

        showToast('🧠 AI is generating your meal plan (30-60s)...', 'info', 10000);
        const result = await apiCall('/meal', 'POST', { kit_id: kitId });

        mealPlanData = result.meal_plan;
        sanitizeMealPlan(mealPlanData); // fix raw ingredient names → proper dishes
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

// ═══ Meal Plan Sanitizer (with anti-repetition across all 7 days) ═══
const RAW_INGREDIENT_SIGNALS = [
    'flour', 'whole)', 'raw ', '100g', 'gram', 'powder', 'seeds', 'leaves',
    'extract', 'oil', 'flakes', '(whole', 'bran', 'husk', 'ml', 'protein'
];
const MEAL_TYPE_KEYWORDS = {
    breakfast: ['breakfast', 'morning'],
    lunch: ['lunch', 'afternoon'],
    dinner: ['dinner', 'night', 'evening meal'],
    snack: ['snack', 'tea', 'mid morning', 'evening snack'],
};

function looksLikeRawIngredient(name) {
    if (!name) return true;
    const n = name.toLowerCase();
    // Raw ingredient signal words
    if (RAW_INGREDIENT_SIGNALS.some(s => n.includes(s))) return true;
    // Very short names (1-2 words) are likely raw ingredients
    if (n.split(' ').length <= 2) return true;
    // Name ends with a meal time word (like "wheat breakfast", "rice dinner")
    const mealTimeWords = ['breakfast', 'lunch', 'dinner', 'snack', 'meal', 'morning', 'evening'];
    if (mealTimeWords.some(w => n.endsWith(w))) return true;
    return false;
}

function mealTypeFromKey(key) {
    const k = key.toLowerCase();
    for (const [cat, words] of Object.entries(MEAL_TYPE_KEYWORDS)) {
        if (words.some(w => k.includes(w))) return cat;
    }
    if (k.includes('breakfast')) return 'breakfast';
    if (k.includes('lunch')) return 'lunch';
    if (k.includes('dinner')) return 'dinner';
    return 'snack';
}

// Build a full shuffled pool of dishes for a meal category across ALL ingredients
// Used dishes are excluded to prevent repetition across all 7 days
function getUniqueDishFor(mealCategory, usedNames) {
    const allIngKeys = Object.keys(INGREDIENT_DISH_MAP).filter(k => k !== '_default');
    const patientKeys = getPatientIngredientKeys();

    // Collect all dishes for this meal category, patient-specific first
    const pool = [];
    [...patientKeys, ...allIngKeys].forEach(key => {
        const map = INGREDIENT_DISH_MAP[key];
        if (!map) return;
        const list = map[mealCategory] || [];
        list.forEach(dish => {
            if (!usedNames.has(dish.name) && !pool.some(p => p.name === dish.name)) {
                pool.push(dish);
            }
        });
    });

    // Shuffle pool so selection isn't always the same
    pool.sort(() => Math.random() - 0.5);
    return pool[0] || null;
}

function sanitizeMealPlan(plan) {
    // Track used dish names across the ENTIRE 7-day plan to prevent repetition
    const usedNames = new Set();

    // First pass: record what the AI generated that looks OK (proper dish names)
    for (let d = 1; d <= 7; d++) {
        const day = plan[`day_${d}`];
        if (!day) continue;
        Object.values(day).forEach(meal => {
            if (meal && typeof meal === 'object' && 'name' in meal && !looksLikeRawIngredient(meal.name)) {
                usedNames.add(meal.name);
            }
        });
    }

    // Second pass: replace bad meals with unique dishes
    for (let d = 1; d <= 7; d++) {
        const dayKey = `day_${d}`;
        const day = plan[dayKey];
        if (!day || typeof day !== 'object') continue;

        Object.keys(day).forEach(mealKey => {
            const meal = day[mealKey];
            if (!meal || typeof meal !== 'object' || !('total_calories' in meal)) return;
            if (!looksLikeRawIngredient(meal.name)) return;

            const cat = mealTypeFromKey(mealKey);
            const dish = getUniqueDishFor(cat, usedNames);
            if (!dish) return;

            usedNames.add(dish.name); // mark as used

            meal.name = dish.name;
            meal.ingredients = dish.ings.split(',').map(i => ({
                name: i.trim(), quantity_g: 'as needed'
            }));
            meal.total_calories = dish.cal;
            meal.protein_g = dish.pro;
            meal.carbs_g = dish.carb;
            meal.fat_g = dish.fat;
            meal.fiber_g = meal.fiber_g || 3;
            meal.prep_time_min = meal.prep_time_min || 15;
            meal.benefits = `Recommended for gut health (IOM yes-list)`;
        });
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

    // Dynamically find all meal objects in the day
    const meals = Object.keys(day).filter(k => day[k] && typeof day[k] === 'object' && 'total_calories' in day[k]);
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
                    <span class="meal-type">${window.customLabels?.[type] || labels[type] || type.replace(/_/g, ' ')}</span>
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
                <div style="margin-top:8px">
                    <button class="btn-swap-meal" style="background:rgba(16,185,129,0.15);color:#10b981;border-color:#10b981" onclick="openYesListChooser('${dayKey}', '${type}')">
                        🥗 Choose from Yes-List
                    </button>
                </div>
            </div>
            <div class="meal-cal-box">
                <span class="cal-value">${cal}</span>
                <span class="cal-label">kcal</span>
            </div>
        </div>`;
    });

    // Removed custom meal button — yes-list chooser per meal provides the flexibility

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

// ═══ Add Custom Meal Feature ═══
let addMealDayTarget = null;

function openAddMealModal(day) {
    addMealDayTarget = day;
    $('addMealType').value = '';
    $('addMealName').value = '';
    $('addMealIngredients').value = '';
    $('addMealCal').value = '0';
    $('addMealPro').value = '0';
    $('addMealCarb').value = '0';
    $('addMealFat').value = '0';
    $('addMealModal').classList.remove('hidden');
}

function closeAddMealModal() {
    $('addMealModal').classList.add('hidden');
    addMealDayTarget = null;
}

function confirmAddMeal() {
    if (!addMealDayTarget) return;
    const type = $('addMealType').value.trim() || 'Custom Meal';
    const name = $('addMealName').value.trim() || 'Unnamed Meal';
    const ings = $('addMealIngredients').value.split(',').map(i => i.trim()).filter(i => i);

    const cal = parseInt($('addMealCal').value) || 0;
    const pro = parseInt($('addMealPro').value) || 0;
    const carb = parseInt($('addMealCarb').value) || 0;
    const fat = parseInt($('addMealFat').value) || 0;

    const newMeal = {
        name: name,
        ingredients: ings.map(ing => ({ name: ing, quantity_g: "N/A" })),
        total_calories: cal,
        protein_g: pro,
        carbs_g: carb,
        fat_g: fat,
        fiber_g: 0,
        prep_time_min: 5,
        benefits: "Custom meal added by Nutritionist"
    };

    let mealKey = type.toLowerCase().replace(/[^a-z0-9]/g, '_');
    if (mealPlanData[addMealDayTarget][mealKey]) {
        mealKey = mealKey + '_' + Math.floor(Math.random() * 1000);
    }

    mealPlanData[addMealDayTarget][mealKey] = newMeal;

    if (!window.customLabels) window.customLabels = {};
    window.customLabels[mealKey] = type;

    renderDay(addMealDayTarget);
    closeAddMealModal();
    showToast(`✅ Added custom meal: "${name}"`, 'success');
}

// ═══ PDF Export (dark premium theme, full 7-day content) ═══
function downloadPDF() {
    if (!mealPlanData) { showToast('⚠️ No meal plan to export.', 'error'); return; }
    const kitId = $('kitId').value.trim() || 'MealPlan';
    showToast('📄 Building PDF... Please wait.', 'info', 5000);

    const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
    const labels = { breakfast: '🌅 Breakfast', mid_morning_snack: '🍎 Mid-Morning Snack', lunch: '☀️ Lunch', evening_snack: '🍶 Evening Snack', dinner: '🌙 Dinner' };

    let body = '';

    // Patient summary block
    if (patientProfile) {
        const p = patientProfile;
        body += `
        <div class="patient-block">
            <h2>Patient Profile</h2>
            <table class="info-table">
                <tr><td>Kit ID</td><td>${p.kit_id || ''}</td><td>Age</td><td>${p.age || 'N/A'}</td></tr>
                <tr><td>Gender</td><td>${p.gender || 'N/A'}</td><td>BMI</td><td>${p.bmi || 'N/A'}</td></tr>
                <tr><td>Diet Type</td><td>${p.diet_type || 'Veg'}</td><td>Location</td><td>${p.location || 'N/A'}</td></tr>
            </table>
            ${p.bacteria_to_increase?.length ? `<p class="bacteria">🦠 Bacteria to Increase: ${p.bacteria_to_increase.filter(b => !b.name.includes('Other')).map(b => b.name).join(', ')}</p>` : ''}
            ${p.avoid_list?.length ? `<p class="avoid">🚫 Avoid: ${p.avoid_list.join(', ')}</p>` : ''}
        </div>`;
    }

    // All 7 days
    for (let d = 1; d <= 7; d++) {
        const dayKey = `day_${d}`;
        const day = mealPlanData[dayKey];
        if (!day) continue;

        const meals = Object.keys(day).filter(k => day[k] && typeof day[k] === 'object' && 'total_calories' in day[k]);
        let dayCalTotal = 0;

        body += `<div class="day-block"><h2>${dayNames[d - 1]}</h2>`;

        meals.forEach(type => {
            const m = day[type];
            if (!m) return;
            const cal = m.total_calories || 0;
            dayCalTotal += cal;
            const ings = (m.ingredients || []).map(i => i.name || i).join(', ');
            const mealLabel = labels[type] || type.replace(/_/g, ' ');

            body += `<div class="meal-block">
                <div class="meal-header">
                    <span class="type-badge">${mealLabel}</span>
                    <span class="mname">${m.name || ''}</span>
                    <span class="cal-badge">${cal} kcal</span>
                </div>
                ${m.benefits ? `<p class="benefits">${m.benefits}</p>` : ''}
                <p class="ings"><span class="label">Ingredients:</span> ${ings}</p>
                <div class="macros">
                    <span>Protein: ${m.protein_g || 0}g</span>
                    <span>Carbs: ${m.carbs_g || 0}g</span>
                    <span>Fat: ${m.fat_g || 0}g</span>
                    <span>Fiber: ${m.fiber_g || 0}g</span>
                </div>
            </div>`;
        });

        body += `<div class="day-total">Daily Total: <strong>${dayCalTotal} kcal</strong></div></div>`;
    }

    const html = `<!DOCTYPE html><html style="background:#0f172a">
<head><meta charset="UTF-8"><title>${kitId} — Meal Plan</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; print-color-adjust:exact; -webkit-print-color-adjust:exact; }
  html, body { background:#0f172a !important; color:#e2e8f0; font-family: Arial, sans-serif; font-size: 11px; padding:20px; }
  h1 { font-size:22px; color:#818cf8; text-align:center; margin-bottom:4px; letter-spacing:1px; }
  .subtitle { text-align:center; color:#64748b; font-size:10px; margin-bottom:24px; }
  .patient-block { background:#1e293b !important; border-left:4px solid #818cf8; padding:12px 16px; margin-bottom:24px; border-radius:8px; }
  .patient-block h2 { font-size:13px; color:#818cf8; margin-bottom:8px; }
  .info-table { width:100%; border-collapse:collapse; font-size:10px; }
  .info-table td { padding:4px 8px; color:#cbd5e1; }
  .info-table td:nth-child(odd) { font-weight:bold; color:#94a3b8; width:16%; }
  .bacteria { color:#34d399; font-size:10px; margin-top:6px; }
  .avoid { color:#f87171; font-size:10px; margin-top:4px; }
  .day-block { margin-bottom:22px; }
  .day-block h2 { font-size:14px; color:#818cf8; border-bottom:1px solid #334155; padding-bottom:5px; margin-bottom:10px; }
  .meal-block { background:#1e293b !important; border:1px solid #334155; border-radius:6px; padding:8px 12px; margin-bottom:7px; }
  .meal-header { display:flex; align-items:center; gap:8px; margin-bottom:4px; flex-wrap:wrap; }
  .type-badge { background:#312e81 !important; color:#a5b4fc; font-size:9px; padding:2px 7px; border-radius:4px; font-weight:bold; white-space:nowrap; }
  .mname { font-size:12px; font-weight:bold; flex:1; color:#f1f5f9; }
  .cal-badge { background:#064e3b !important; color:#34d399; font-size:10px; padding:2px 8px; border-radius:4px; font-weight:bold; white-space:nowrap; }
  .benefits { font-size:9px; color:#34d399; margin:3px 0; }
  .ings { font-size:10px; color:#94a3b8; margin:3px 0; }
  .label { font-weight:bold; color:#64748b; }
  .macros { display:flex; gap:10px; font-size:9px; color:#64748b; margin-top:5px; flex-wrap:wrap; }
  .macros span { background:#0f172a !important; padding:2px 6px; border-radius:4px; color:#94a3b8; }
  .day-total { text-align:right; font-size:11px; color:#64748b; margin-top:5px; border-top:1px solid #334155; padding-top:4px; }
  .day-total strong { color:#818cf8; }
</style></head>
<body>
<h1>🌱 NutriGenie — 7-Day Personalized Meal Plan</h1>
<p class="subtitle">Kit ID: ${kitId} • Generated: ${new Date().toLocaleDateString('en-IN')} • Powered by IOM Bioworks • AWS Bedrock + RAG</p>
${body}
</body></html>`;

    const opt = {
        margin: 0.35,
        filename: `${kitId}_Meal_Plan.pdf`,
        image: { type: 'jpeg', quality: 0.97 },
        html2canvas: { scale: 2, backgroundColor: '#0f172a', useCORS: true },
        jsPDF: { unit: 'in', format: 'a4', orientation: 'portrait' }
    };

    html2pdf().set(opt).from(html).save().then(() => {
        showToast('✅ PDF Downloaded!', 'success');
    });
}

// ═══ Yes-List Food Chooser (ingredient-based, rotates by day) ═══
function getMealCategory(mealType) {
    const t = mealType.toLowerCase();
    if (t.includes('breakfast')) return 'breakfast';
    if (t.includes('lunch')) return 'lunch';
    if (t.includes('dinner')) return 'dinner';
    return 'snack';
}

// Rotate ingredient by BOTH day AND meal slot — so each meal in a day gets a different ingredient
// e.g. Day1: breakfast=oats, lunch=ragi, snack=curd, dinner=whole wheat
//      Day2: breakfast=moong, lunch=bajra, snack=flaxseed, dinner=banana
const MEAL_SLOT_ORDER = ['breakfast', 'snack', 'lunch', 'dinner'];

function getIngredientForDayAndMeal(dayKey, mealCategory) {
    const ingKeys = getPatientIngredientKeys();
    const dayNum = parseInt(dayKey.replace('day_', '')) - 1;
    const slotIndex = MEAL_SLOT_ORDER.indexOf(mealCategory);
    const slot = slotIndex >= 0 ? slotIndex : 0;
    // Offset by both day and slot to get true variety
    const index = (dayNum * MEAL_SLOT_ORDER.length + slot) % ingKeys.length;
    return ingKeys[index] || '_default';
}

function openYesListChooser(dayKey, mealType) {
    const category = getMealCategory(mealType);
    const ingredientKey = getIngredientForDayAndMeal(dayKey, category);
    const ingredientData = INGREDIENT_DISH_MAP[ingredientKey] || INGREDIENT_DISH_MAP['_default'];
    const rawFoods = ingredientData[category] || ingredientData.lunch || ingredientData.dinner || [];
    // Include _default foods for extra variety, skip duplicates
    const defaultFoods = (INGREDIENT_DISH_MAP['_default'][category] || []).filter(
        df => !rawFoods.some(f => f.name === df.name)
    );
    const foods = [...rawFoods, ...defaultFoods];
    if (!foods.length) { showToast('⚠️ No suggestions available.', 'error'); return; }

    const categoryLabels = { breakfast: '🌅 Breakfast', lunch: '☀️ Lunch', snack: '🍎 Snack', dinner: '🌙 Dinner' };
    const dayNum = parseInt(dayKey.replace('day_', ''));
    const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const dayLabel = dayNames[dayNum - 1] || dayKey;

    let html = `<div class="modal-overlay" id="yesListModal" onclick="if(event.target===this)closeYesListModal()">
        <div class="modal-card" style="max-height:80vh;overflow-y:auto;width:480px">
            <div class="modal-header">
                <h3>🥗 ${categoryLabels[category] || 'Meal'} — ${dayLabel} Yes-List</h3>
                <button class="modal-close" onclick="closeYesListModal()">✕</button>
            </div>
            <p style="padding:4px 20px 10px;font-size:0.76rem;color:var(--text-muted)">
                Today's featured ingredient: <strong style="color:var(--success)">${ingredientData.label}</strong><br>
                Tap any dish to replace the current ${category} with it.
            </p>
            <div class="modal-body" style="padding:6px 14px">`;

    foods.forEach((f, i) => {
        html += `<div onclick="replaceWithYesListFood('${dayKey}','${mealType}',${i})" style="
            background:var(--bg-glass); border:1px solid var(--border); border-radius:8px;
            padding:10px 13px; margin-bottom:6px; cursor:pointer; transition:all 0.2s;"
            onmouseover="this.style.borderColor='#10b981';this.style.transform='translateX(4px)'"
            onmouseout="this.style.borderColor='var(--border)';this.style.transform='none'">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <strong style="font-size:0.9rem">${esc(f.name)}</strong>
                <span style="font-size:0.75rem;color:#10b981;background:rgba(16,185,129,0.12);padding:2px 8px;border-radius:6px">${f.cal} kcal</span>
            </div>
            <div style="font-size:0.72rem;color:var(--text-muted);margin-top:3px">${esc(f.ings)}</div>
            <div style="display:flex;gap:10px;margin-top:4px;font-size:0.68rem;color:var(--text-secondary)">
                <span>P:${f.pro}g</span> <span>C:${f.carb}g</span> <span>F:${f.fat}g</span>
            </div>
        </div>`;
    });

    html += `</div></div></div>`;
    window._yesListFoods = foods;
    document.body.insertAdjacentHTML('beforeend', html);
}

function closeYesListModal() {
    const m = document.getElementById('yesListModal');
    if (m) m.remove();
}

function replaceWithYesListFood(dayKey, mealType, foodIndex) {
    const f = window._yesListFoods?.[foodIndex];
    if (!f || !mealPlanData?.[dayKey]) return;

    const ingredientKey = getIngredientForDayAndMeal(dayKey, getMealCategory(mealType));
    const ingredientData = INGREDIENT_DISH_MAP[ingredientKey] || {};

    const newMeal = {
        name: f.name,
        ingredients: (f.ings || '').split(',').map(ing => ({ name: ing.trim(), quantity_g: 'as needed' })),
        total_calories: f.cal,
        protein_g: f.pro,
        carbs_g: f.carb,
        fat_g: f.fat || 0,
        fiber_g: 3,
        prep_time_min: 15,
        benefits: `From yes-list ingredient: ${ingredientData.label || 'IOM recommendation'}`
    };

    mealPlanData[dayKey][mealType] = newMeal;
    closeYesListModal();
    renderDay(dayKey);
    showToast(`✅ Replaced with "${f.name}"!`, 'success');
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
