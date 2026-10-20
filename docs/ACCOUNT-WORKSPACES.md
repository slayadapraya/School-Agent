# Account and workspace controls

## Navigation

On desktop, Collapse sidebar changes the navigation into a 56 px rail. The logo opens
Home; Chats opens the most recently visited available conversation, falling back to the
latest account-owned conversation. New thread uses the normal subject/account rules.
The expanded width and compact preference are saved per account in browser storage.
Phones retain their navigation drawer.

Hover labels appear after 200 ms. Hovering Chats opens its recent-conversation fly-out
after 150 ms, with up to 20 conversations from the signed-in account's bootstrap list.
Leaving the fly-out dismisses it after a short grace period; clicking or Escape closes it.

## Profile and pictures

The profile menu has a separate account card, navigation shortcuts and a Settings/footer
area. The account card opens name/password settings and the profile-picture controls.
Pictures and preset icons save immediately. Name/password changes use Save account.
Neither picture saves nor ordinary account saves rebuild the chat DOM, so scroll,
unsent text, selected panels and editor state remain in place. Password changes revoke
sessions and require signing in again.

Uploads accept JPEG, PNG and WebP, up to 2 MB and 16 million pixels. Pillow validates the
image and the server stores a 128 × 128 JPEG with upload metadata discarded. SVG and
arbitrary URLs are not accepted. A small preset icon or initials can replace the image.
The avatar endpoint always uses the authenticated account; a supplied user ID cannot
target another account. Avatars are separate from teaching files and model context.

## Read-only student workspaces

Staff studio → Student workspaces uses the existing staff roster, record and note GET
endpoints. It never switches the authenticated identity or creates a student session.
Teachers see students and records permitted by their existing assignments and course
rules; administrators can review student records. Opening chats and note bodies uses
the existing audit events. Staff/private record protections remain in place.

The review surface has a student selector, chat/note list and content pane. It mounts
no student composer or editable note controls. The personal chat/note write endpoints
continue to check ownership, including when the caller is an administrator.

## Editable source

- `app/static/sidebar-resize.js`, `artifacts.css`: compact navigation and width controls.
- `app/static/navigation-hover.js`, `account-ui.css`: hover help and recent chats.
- `app/static/account-ui.js`, `app/preferences.py`: account picture UI, validation and storage.
- `app/static/student-review.js`, `admin.js`: read-only student review and Staff studio tabs.
- `app/static/app.js`: account identity refresh and normal navigation.
