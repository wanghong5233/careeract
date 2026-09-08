import { betterAuth } from "better-auth";
import { jwt } from "better-auth/plugins";
import { Pool } from "pg";

import { serverEnv } from "@/lib/server-env";

const TOKEN_EXPIRATION = "15m";

function createAuth() {
  const database = new Pool({
    connectionString: serverEnv.authDatabaseUrl,
    options: "-c search_path=auth",
  });

  return betterAuth({
    appName: "CareerAct",
    baseURL: serverEnv.betterAuthUrl,
    trustedOrigins: [serverEnv.betterAuthUrl],
    secret: serverEnv.betterAuthSecret,
    database,
    emailAndPassword: {
      enabled: true,
    },
    plugins: [
      jwt({
        jwt: {
          issuer: serverEnv.betterAuthUrl,
          audience: serverEnv.betterAuthUrl,
          expirationTime: TOKEN_EXPIRATION,
          definePayload: ({ user }) => ({ email: user.email }),
        },
      }),
    ],
  });
}

type Auth = ReturnType<typeof createAuth>;

let authInstance: Auth | undefined;

export function getAuth(): Auth {
  authInstance ??= createAuth();
  return authInstance;
}
