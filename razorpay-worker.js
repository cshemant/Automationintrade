/**
 * Cloudflare Worker: Razorpay order + verify API for Automation In Trade
 * --------------------------------------------------------------------
 * Routes expected by website script.js:
 *   POST /api/razorpay/order
 *   POST /api/razorpay/verify
 *
 * Required Worker secrets / variables:
 *   RAZORPAY_KEY_ID      = your Razorpay key id
 *   RAZORPAY_KEY_SECRET  = your Razorpay key secret
 *
 * Important fix in this version:
 *   ₹9,999 is now included in ALLOWED_AMOUNTS_INR for Stock Research Premium.
 */

const ALLOWED_AMOUNTS_INR = new Set([1, 499, 2999, 4999, 7999, 9999]);
const CURRENCY = 'INR';

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'access-control-allow-origin': '*',
      'access-control-allow-methods': 'POST, OPTIONS',
      'access-control-allow-headers': 'Content-Type'
    }
  });
}

function normalizeAmount(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return null;
  return Math.round(amount);
}

function validateAmount(amount) {
  if (!ALLOWED_AMOUNTS_INR.has(amount)) {
    const allowed = [...ALLOWED_AMOUNTS_INR].sort((a, b) => a - b).map(n => `₹${n.toLocaleString('en-IN')}`).join(', ');
    throw new Error(`Invalid amount. Only ${allowed} are allowed.`);
  }
}

function requireEnv(env) {
  if (!env.RAZORPAY_KEY_ID || !env.RAZORPAY_KEY_SECRET) {
    throw new Error('Razorpay Worker secrets are missing. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.');
  }
}

function razorpayAuth(env) {
  return 'Basic ' + btoa(`${env.RAZORPAY_KEY_ID}:${env.RAZORPAY_KEY_SECRET}`);
}

async function readJson(request) {
  try {
    return await request.json();
  } catch (error) {
    throw new Error('Invalid JSON request body.');
  }
}

async function createOrder(request, env) {
  requireEnv(env);
  const body = await readJson(request);
  const amount = normalizeAmount(body.amount);
  validateAmount(amount);

  const tool = String(body.tool || 'Automation In Trade Tool').slice(0, 120);
  const plan = String(body.plan || 'Tool Access').slice(0, 120);
  const receipt = `ait_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  const response = await fetch('https://api.razorpay.com/v1/orders', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'authorization': razorpayAuth(env)
    },
    body: JSON.stringify({
      amount: amount * 100,
      currency: CURRENCY,
      receipt,
      payment_capture: 1,
      notes: {
        tool_name: tool,
        plan_name: plan,
        website: String(body.website || 'https://automationintrade.com/').slice(0, 180)
      }
    })
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error?.description || data.error?.reason || 'Razorpay order creation failed.');
  }

  return jsonResponse({
    ok: true,
    order_id: data.id,
    amount,
    currency: CURRENCY,
    receipt
  });
}

async function hmacSha256Hex(message, secret) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(message));
  return [...new Uint8Array(signature)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

function safeEqual(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i += 1) result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return result === 0;
}

async function verifyPayment(request, env) {
  requireEnv(env);
  const body = await readJson(request);

  const orderId = String(body.razorpay_order_id || '');
  const paymentId = String(body.razorpay_payment_id || '');
  const receivedSignature = String(body.razorpay_signature || '');
  const amount = normalizeAmount(body.amount);
  validateAmount(amount);

  if (!orderId || !paymentId || !receivedSignature) {
    throw new Error('Missing Razorpay verification fields.');
  }

  const expectedSignature = await hmacSha256Hex(`${orderId}|${paymentId}`, env.RAZORPAY_KEY_SECRET);
  if (!safeEqual(expectedSignature, receivedSignature)) {
    return jsonResponse({ ok: false, error: 'Payment signature verification failed.' }, 400);
  }

  let captureStatus = 'verified';

  // payment_capture: 1 usually auto-captures the payment. This extra capture call is safe-handled.
  const captureResponse = await fetch(`https://api.razorpay.com/v1/payments/${paymentId}/capture`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'authorization': razorpayAuth(env)
    },
    body: JSON.stringify({ amount: amount * 100, currency: CURRENCY })
  });

  const captureData = await captureResponse.json().catch(() => ({}));
  if (captureResponse.ok) {
    captureStatus = captureData.status || 'captured';
  } else {
    const description = String(captureData.error?.description || '').toLowerCase();
    if (description.includes('already') || description.includes('captured')) {
      captureStatus = 'already_captured';
    } else {
      captureStatus = 'verified_capture_check_failed';
    }
  }

  return jsonResponse({
    ok: true,
    verified: true,
    capture_status: captureStatus,
    payment_status: captureStatus
  });
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return jsonResponse({ ok: true });

    const url = new URL(request.url);

    try {
      if (request.method === 'POST' && url.pathname.endsWith('/api/razorpay/order')) {
        return await createOrder(request, env);
      }
      if (request.method === 'POST' && url.pathname.endsWith('/api/razorpay/verify')) {
        return await verifyPayment(request, env);
      }
      return jsonResponse({ ok: true, service: 'Automation In Trade Razorpay API', allowedAmounts: [...ALLOWED_AMOUNTS_INR].sort((a, b) => a - b) });
    } catch (error) {
      return jsonResponse({ ok: false, error: error.message || 'Payment API error.' }, 400);
    }
  }
};
