window.PEOPLE_MEMORY_CONFIG = {
  // Hosted: https://YOUR_PROJECT.supabase.co
  // Local:  http://127.0.0.1:54321
  supabaseUrl: "http://127.0.0.1:54321",

  // This is the publishable/anon browser key, never the service-role key.
  supabaseKey: "PASTE_YOUR_PUBLISHABLE_KEY",

  // Set false until the Google OAuth provider is configured in Supabase Auth.
  googleOAuth: false,

  // Disable after creating the single owner account.
  allowSignup: true,

  // Set false to hide the email/password form and leave Google as the only way
  // in. Match it to the Supabase email provider: if that is off, this is false.
  passwordLogin: true,

  // Optional integration, off by default. Turn it on only if the same database also
  // carries a location archive from tars-location-mcp
  // (https://github.com/michelgrolet/tars-location-mcp): the record card then gets a
  // "With me" block where a date range on a person resolves, from that archive, into
  // where the two of you actually were. Without those tables the block stays hidden.
  locationCompanions: false,
};
