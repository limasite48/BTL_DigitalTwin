package com.huylq.iotprojectserver.security;

import com.huylq.iotprojectserver.common.error.ErrorType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.web.filter.OncePerRequestFilter;
import tools.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.util.Arrays;

@RequiredArgsConstructor
public class DeviceRegistrationFilter extends OncePerRequestFilter {

  private final DeviceRegistrationService registrationService;
  private final ObjectMapper objectMapper;

  private static final String[] BYPASS_PATHS = {
      "/api/v1/auth/device/",
      "/api/v1/auth/login",
      "/api/v1/auth/refresh",
      "/api/v1/auth/logout",
      "/api/v1/.well-known/jwks.json",
      "/actuator/health",
      "/actuator/info",
      "/api/v1/api-docs",
      "/swagger-ui"
  };

  @Override
  protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
      throws ServletException, IOException {

    String path = request.getRequestURI();

    // Bypass check
    boolean bypass = Arrays.stream(BYPASS_PATHS).anyMatch(path::contains);
    if (bypass) {
      filterChain.doFilter(request, response);
      return;
    }

    String deviceUuid = request.getHeader("X-Device-UUID");

    if (!registrationService.isAllowed(deviceUuid)) {
      writeProblem(response, HttpServletResponse.SC_FORBIDDEN, ErrorType.FORBIDDEN,
          "Chỉ thiết bị đăng ký trước mới được phép truy cập điều khiển hệ thống lúc này.", path);
      return;
    }

    filterChain.doFilter(request, response);
  }

  private void writeProblem(HttpServletResponse res, int status, ErrorType type, String detail, String path) throws IOException {
    ProblemDetail pd = ProblemDetail.forStatus(status);
    pd.setType(type.uri());
    pd.setTitle("Forbidden Device");
    pd.setDetail(detail);
    pd.setInstance(URI.create(path));
    res.setStatus(status);
    res.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
    res.setCharacterEncoding("UTF-8");
    res.getWriter().write(objectMapper.writeValueAsString(pd));
  }
}
