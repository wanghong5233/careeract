const requireEnvironmentVariable = (name: string): string => {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
};

export const serverEnv = {
  apiBaseUrl: requireEnvironmentVariable("API_BASE_URL"),
  authDatabaseUrl: requireEnvironmentVariable("AUTH_DATABASE_URL"),
  betterAuthSecret: requireEnvironmentVariable("BETTER_AUTH_SECRET"),
  betterAuthUrl: requireEnvironmentVariable("BETTER_AUTH_URL"),
} as const;
