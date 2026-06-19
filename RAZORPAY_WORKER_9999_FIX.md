# Razorpay ₹9,999 Payment Fix

The website frontend now shows **Unlock ₹9,999**, but the live Razorpay Worker/API is still allowing only old amounts like ₹1, ₹499 and ₹4,999. That is why the error appears:

> Invalid amount. Only ₹1, ₹499 and ₹4,999 are allowed.

## What to update

Update the Cloudflare Worker that handles this route:

```text
https://automationintrade.com/api/razorpay/order
```

Use the included file:

```text
razorpay-worker.js
```

This file allows these amounts:

```text
₹1, ₹499, ₹2,999, ₹4,999, ₹7,999, ₹9,999
```

## Cloudflare steps

1. Open Cloudflare Dashboard.
2. Go to **Workers & Pages**.
3. Open the Worker that is mapped to `automationintrade.com/api/razorpay/*`.
4. Click **Edit code**.
5. Replace the old Worker code with `razorpay-worker.js` from this package.
6. Keep the same Worker secrets/variables:

```text
RAZORPAY_KEY_ID
RAZORPAY_KEY_SECRET
```

7. Click **Deploy**.
8. Test the premium button again.

## Important

Uploading only the static website zip will not fix this error. The static website price and the Worker amount whitelist must both match.
