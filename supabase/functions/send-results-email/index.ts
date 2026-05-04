import { serve } from "https://deno.land/std/http/server.ts";
import nodemailer from "npm:nodemailer";

serve(async (req) => {
  try {
    const { name, email, city, score } = await req.json();

    if (!name || !email || !city || score === undefined) {
      return new Response(
        JSON.stringify({ error: "Missing required fields" }),
        { status: 400 }
      );
    }

    const transporter = nodemailer.createTransport({
      host: Deno.env.get("SMTP_HOST"),
      port: 587,
      secure: false,
      auth: {
        user: Deno.env.get("SMTP_USER"),
        pass: Deno.env.get("SMTP_PASS"),
      },
    });

    await transporter.sendMail({
      from: "City Explorer <no-reply@cityexplorer>",
      to: email,
      subject: "Your City Explorer Results",
      text: `
Hello ${name},

Congratulations on completing the City Explorer game!

City played: ${city}
Final score: ${score}

Thank you for taking part.

– City Explorer Team
`,
    });

    return new Response(
      JSON.stringify({ success: true }),
      { headers: { "Content-Type": "application/json" } }
    );

  } catch (err) {
    return new Response(
      JSON.stringify({ error: "Email failed to send" }),
      { status: 500 }
    );
  }
});
