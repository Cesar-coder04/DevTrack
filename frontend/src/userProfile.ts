export interface UserProfile {
  id: number;
  username: string;
  email: string;
  display_name: string;
  bio: string | null;
  avatar_key: string | null;
  is_active: boolean;
  email_verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export function isUserProfile(value: unknown): value is UserProfile {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const profile = value as Record<string, unknown>;

  return (
    typeof profile.id === "number" &&
    typeof profile.username === "string" &&
    typeof profile.email === "string" &&
    typeof profile.display_name === "string" &&
    (typeof profile.bio === "string" || profile.bio === null) &&
    (typeof profile.avatar_key === "string" || profile.avatar_key === null) &&
    typeof profile.is_active === "boolean" &&
    (typeof profile.email_verified_at === "string" ||
      profile.email_verified_at === null) &&
    typeof profile.created_at === "string" &&
    typeof profile.updated_at === "string"
  );
}
