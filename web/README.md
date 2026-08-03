# Web app

The web app talks directly to Supabase. Row-level security keeps it private.

1. Copy `config.example.js` to `config.js`.
2. Add the project URL and the **publishable** key. Never use the service-role key.
3. Set the owner email in `app_settings`:

   ```sql
   update app_settings set value = 'you@example.com' where key = 'owner_email';
   ```

4. Serve the folder:

   ```bash
   python3 -m http.server 4173 --directory web
   ```

For hosted deployments, publish `web/` to any static host and keep `config.js` out of Git.
