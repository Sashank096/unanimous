import { Webhook } from "https://esm.sh/standardwebhooks@1.0.0";

type AuthEmailPayload = {
  user?: {
    email?: string;
    new_email?: string;
  };
  email_data?: {
    email_action_type?: string;
    token?: string;
    token_new?: string;
  };
};

type EmailDelivery = {
  to: string;
  token?: string;
};

const escapeHtml = (value: string) =>
  value.replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[
        character
      ] ?? character,
  );

const sendEmail = async (
  resendApiKey: string,
  fromEmail: string,
  delivery: EmailDelivery,
  actionType: string,
) => {
  const subject = delivery.token
    ? "Your U_NANI_MOUS verification code"
    : "A security update to your U_NANI_MOUS account";
  const content = delivery.token
    ? `
      <p>Enter this one-time verification code:</p>
      <p style="font-size:32px;font-weight:700;letter-spacing:8px">${escapeHtml(delivery.token)}</p>
      <p>This code expires shortly. If you did not request it, ignore this email.</p>
    `
    : `<p>A security update (${escapeHtml(actionType)}) was requested for your account. If you did not request it, secure your account.</p>`;
  const text = delivery.token
    ? `Your U_NANI_MOUS verification code is ${delivery.token}. If you did not request it, ignore this email.`
    : `A security update (${actionType}) was requested for your U_NANI_MOUS account. If you did not request it, secure your account.`;

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${resendApiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: fromEmail,
      to: [delivery.to],
      subject,
      text,
      html: `
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto">
          <h2>U_NANI_MOUS account</h2>
          ${content}
        </div>
      `,
    }),
  });

  if (!response.ok) {
    const details = await response.text();
    console.error("Resend rejected auth email", response.status, details);
    throw new Error("Email provider rejected the message");
  }
};

Deno.serve(async (request) => {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const resendApiKey = Deno.env.get("RESEND_API_KEY");
  const fromEmail = Deno.env.get("RESEND_FROM_EMAIL");
  const configuredSecrets = Deno.env.get("SEND_EMAIL_HOOK_SECRETS");
  if (!resendApiKey || !fromEmail || !configuredSecrets) {
    console.error("Missing Resend or Send Email Hook configuration");
    return new Response("Email delivery is not configured", { status: 500 });
  }

  const secrets = configuredSecrets
    .split("|")
    .map((secret) => secret.trim().replace(/^v1,whsec_/, ""))
    .filter(Boolean);
  if (secrets.length === 0) {
    console.error("No valid Send Email Hook secret is configured");
    return new Response("Email delivery is not configured", { status: 500 });
  }

  const body = await request.text();
  const headers = Object.fromEntries(request.headers);
  let payload: AuthEmailPayload | undefined;
  for (const secret of secrets) {
    try {
      payload = new Webhook(secret).verify(body, headers) as AuthEmailPayload;
      break;
    } catch {
      // Try another configured secret during key rotation.
    }
  }
  if (!payload) {
    return new Response("Invalid Send Email Hook signature", { status: 401 });
  }

  const email = payload.user?.email?.trim();
  const newEmail = payload.user?.new_email?.trim();
  const actionType = payload.email_data?.email_action_type?.trim() || "authentication";
  const token = payload.email_data?.token?.trim();
  const tokenNew = payload.email_data?.token_new?.trim();
  const deliveries: EmailDelivery[] = [];

  if (actionType === "email_change" && newEmail && token && tokenNew && email) {
    deliveries.push({ to: email, token }, { to: newEmail, token: tokenNew });
  } else {
    const recipient = actionType === "email_change" ? newEmail || email : email;
    if (!recipient) {
      console.error("Send Email Hook payload is missing a recipient email");
      return new Response("Missing recipient email", { status: 400 });
    }
    deliveries.push({ to: recipient, token: token || tokenNew || undefined });
  }

  try {
    await Promise.all(
      deliveries.map((delivery) =>
        sendEmail(resendApiKey, fromEmail, delivery, actionType)
      ),
    );
  } catch {
    return new Response("Email provider rejected the message", { status: 502 });
  }

  return new Response(null, { status: 200 });
});
