export type OdinUser = {
  id: number;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
};

export type AuthResponse = {
  user: OdinUser;
  authenticated: true;
};
