import Link from "next/link";

import { auth } from "@/auth";

export default async function Page() {
  const session = await auth();
  return (
    <main className="min-h-screen p-8">
      <h1 className="text-3xl font-bold">Trip Concierge</h1>
      {session?.user ? (
        <p className="mt-4">Signed in as {session.user.email ?? session.user.name}.</p>
      ) : (
        <p className="mt-4">
          <Link href="/login" className="underline">
            Sign in
          </Link>
        </p>
      )}
    </main>
  );
}
