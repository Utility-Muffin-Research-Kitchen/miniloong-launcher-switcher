#include <SDL.h>
#include <SDL_ttf.h>

#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static volatile sig_atomic_t g_running = 1;

static void handle_signal(int signal_id) {
    (void)signal_id;
    g_running = 0;
}

static FILE *open_log(void) {
    FILE *file = fopen("/userdata/umrk-launcher.log", "a");
    if (file == NULL) {
        file = stderr;
    }
    return file;
}

static void log_line(FILE *log, const char *message) {
    time_t now = time(NULL);
    struct tm tm_now;
    char stamp[32] = "unknown";
    if (localtime_r(&now, &tm_now) != NULL) {
        strftime(stamp, sizeof(stamp), "%F %T", &tm_now);
    }
    fprintf(log, "[%s] poc: %s\n", stamp, message);
    fflush(log);
}

static TTF_Font *open_font(int size) {
    const char *env_font = getenv("UMRK_POC_FONT");
    const char *candidates[] = {
        env_font,
        "/tmp/umrk-launcher/res/font.ttf",
        "/mnt/sdcard/umrk-launcher/res/font.ttf",
        "/loong/default_font.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        NULL,
    };

    for (int i = 0; candidates[i] != NULL; i++) {
        if (candidates[i][0] == '\0') {
            continue;
        }
        TTF_Font *font = TTF_OpenFont(candidates[i], size);
        if (font != NULL) {
            return font;
        }
    }
    return NULL;
}

static void draw_text(SDL_Renderer *renderer, TTF_Font *font, const char *text, int x, int y, SDL_Color color) {
    if (font == NULL || text == NULL) {
        return;
    }

    SDL_Surface *surface = TTF_RenderUTF8_Blended(font, text, color);
    if (surface == NULL) {
        return;
    }

    SDL_Texture *texture = SDL_CreateTextureFromSurface(renderer, surface);
    if (texture != NULL) {
        SDL_Rect dst = {x, y, surface->w, surface->h};
        SDL_RenderCopy(renderer, texture, NULL, &dst);
        SDL_DestroyTexture(texture);
    }

    SDL_FreeSurface(surface);
}

static int env_int(const char *name, int fallback) {
    const char *value = getenv(name);
    if (value == NULL || value[0] == '\0') {
        return fallback;
    }
    char *end = NULL;
    long parsed = strtol(value, &end, 10);
    if (end == value || parsed < 0 || parsed > 2147483647L) {
        return fallback;
    }
    return (int)parsed;
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    FILE *log = open_log();
    log_line(log, "starting");

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS | SDL_INIT_TIMER) != 0) {
        fprintf(log, "SDL_Init failed: %s\n", SDL_GetError());
        return 1;
    }
    if (TTF_Init() != 0) {
        fprintf(log, "TTF_Init failed: %s\n", TTF_GetError());
        SDL_Quit();
        return 1;
    }

    const int width = env_int("UMRK_POC_WIDTH", 720);
    const int height = env_int("UMRK_POC_HEIGHT", 960);
    const int exit_ms = env_int("UMRK_POC_EXIT_MS", 0);

    SDL_Window *window = SDL_CreateWindow(
        "UMRK Launcher Switcher POC",
        SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED,
        width,
        height,
        SDL_WINDOW_FULLSCREEN_DESKTOP | SDL_WINDOW_SHOWN);
    if (window == NULL) {
        fprintf(log, "SDL_CreateWindow failed: %s\n", SDL_GetError());
        TTF_Quit();
        SDL_Quit();
        return 1;
    }

    SDL_Renderer *renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (renderer == NULL) {
        renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    }
    if (renderer == NULL) {
        fprintf(log, "SDL_CreateRenderer failed: %s\n", SDL_GetError());
        SDL_DestroyWindow(window);
        TTF_Quit();
        SDL_Quit();
        return 1;
    }

    TTF_Font *title_font = open_font(42);
    TTF_Font *body_font = open_font(24);
    TTF_Font *small_font = open_font(18);

    Uint32 started = SDL_GetTicks();
    int frame = 0;
    while (g_running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) {
                g_running = 0;
            } else if (event.type == SDL_KEYDOWN) {
                const char *name = SDL_GetKeyName(event.key.keysym.sym);
                fprintf(log, "[input] key=%s\n", name != NULL ? name : "unknown");
                fflush(log);
                if (event.key.keysym.sym == SDLK_ESCAPE || event.key.keysym.sym == SDLK_q) {
                    g_running = 0;
                }
            }
        }

        if (exit_ms > 0 && (int)(SDL_GetTicks() - started) >= exit_ms) {
            g_running = 0;
        }

        SDL_SetRenderDrawColor(renderer, 18, 24, 30, 255);
        SDL_RenderClear(renderer);

        SDL_Rect header = {34, 44, width - 68, 168};
        SDL_SetRenderDrawColor(renderer, 51, 88, 112, 255);
        SDL_RenderFillRect(renderer, &header);

        SDL_Rect status = {34, 242, width - 68, 220};
        SDL_SetRenderDrawColor(renderer, 36, 45, 54, 255);
        SDL_RenderFillRect(renderer, &status);

        SDL_Rect accent = {34, 500, width - 68, 320};
        SDL_SetRenderDrawColor(renderer, 114, 84, 52, 255);
        SDL_RenderFillRect(renderer, &accent);

        SDL_Color white = {244, 247, 250, 255};
        SDL_Color muted = {196, 207, 214, 255};
        SDL_Color warm = {255, 221, 160, 255};

        draw_text(renderer, title_font, "UMRK Launcher", 60, 74, white);
        draw_text(renderer, body_font, "marker-gated loong_pangu replacement", 62, 142, muted);

        draw_text(renderer, body_font, "POC launcher is running from the switcher path.", 60, 278, white);
        draw_text(renderer, body_font, "Stock services stay alive; only the GUI entrypoint changes.", 60, 326, muted);
        draw_text(renderer, small_font, "Q or Escape exits in test mode. Power controls remain stock-owned.", 60, 392, muted);

        char frame_text[96];
        snprintf(frame_text, sizeof(frame_text), "Wayland SDL2 frame %d", frame++);
        draw_text(renderer, body_font, frame_text, 60, 548, warm);
        draw_text(renderer, body_font, "Next step: package Jawaka behind this same contract.", 60, 604, white);
        draw_text(renderer, small_font, "Bundle: /mnt/sdcard/umrk-launcher -> /tmp/umrk-launcher", 60, 704, muted);

        SDL_RenderPresent(renderer);
        SDL_Delay(16);
    }

    log_line(log, "exiting");

    if (title_font != NULL) {
        TTF_CloseFont(title_font);
    }
    if (body_font != NULL) {
        TTF_CloseFont(body_font);
    }
    if (small_font != NULL) {
        TTF_CloseFont(small_font);
    }
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    TTF_Quit();
    SDL_Quit();

    if (log != stderr) {
        fclose(log);
    }
    return 0;
}

