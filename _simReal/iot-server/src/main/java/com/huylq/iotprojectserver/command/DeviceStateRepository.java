package com.huylq.iotprojectserver.command;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.OffsetDateTime;
import java.util.List;

public interface DeviceStateRepository extends JpaRepository<DeviceState, String> {

  /**
   * {@code ?zone=} joins {@code devices} (zone isn't stored on the mirror); {@code
   * ?drifted=true} serves off the partial drift index (System Design §5.11) — {@code
   * IS DISTINCT FROM} treats {@code NULL} desired/reported as a real difference, matching
   * the index predicate exactly. {@code JOIN FETCH} avoids N+1 when the caller reads
   * {@code device.zone} per row.
   */
  @Query("""
      SELECT d FROM DeviceState d JOIN FETCH d.device dev
      WHERE (CAST(:zone AS string) IS NULL OR dev.zone = :zone)
        AND (:drifted = false OR d.desiredState IS DISTINCT FROM d.reportedState)
      ORDER BY dev.zone, d.deviceId
      """)
  List<DeviceState> findAllFiltered(@Param("zone") String zone, @Param("drifted") boolean drifted);

  /**
   * Upsert on command issue (System Design §5.8) — updates {@code desiredState} +
   * traceability columns, leaves {@code reportedState} untouched.
   */
  @Modifying
  @Query(value = """
      INSERT INTO device_state (device_id, desired_state, attributes, last_command_id, commanded_at, updated_at)
      VALUES (:deviceId, :desiredState, CAST(:attributesJson AS jsonb), :commandId, :commandedAt, now())
      ON CONFLICT (device_id) DO UPDATE SET
          desired_state   = EXCLUDED.desired_state,
          attributes      = EXCLUDED.attributes,
          last_command_id = EXCLUDED.last_command_id,
          commanded_at    = EXCLUDED.commanded_at,
          updated_at      = now()
      """, nativeQuery = true)
  int upsertDesired(@Param("deviceId") String deviceId, @Param("desiredState") String desiredState,
                    @Param("attributesJson") String attributesJson, @Param("commandId") String commandId,
                    @Param("commandedAt") OffsetDateTime commandedAt);

  @Modifying
  @Query(value = """
      INSERT INTO device_state (device_id, desired_state, updated_at)
      VALUES (:deviceId, :desiredState, now())
      ON CONFLICT (device_id) DO UPDATE SET
          desired_state = EXCLUDED.desired_state,
          updated_at    = now()
      """, nativeQuery = true)
  int upsertDesiredStateOnly(@Param("deviceId") String deviceId, @Param("desiredState") String desiredState);

  /**
   * Upsert on terminal-success ack (System Design §5.8) — updates only {@code
   * reportedState}; a first-ever row for this device gets the {@code attributes} column
   * default ({@code '{}'}) since it's omitted from the insert list.
   */
  @Modifying
  @Query(value = """
      INSERT INTO device_state (device_id, reported_state, updated_at)
      VALUES (:deviceId, :reportedState, now())
      ON CONFLICT (device_id) DO UPDATE SET
          reported_state = EXCLUDED.reported_state,
          updated_at     = now()
      """, nativeQuery = true)
  int upsertReported(@Param("deviceId") String deviceId, @Param("reportedState") String reportedState);
}
