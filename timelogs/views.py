# timelogs/views.py
from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import TimeLog, TimeLogSegment, Location
from .utils import haversine_m

def _nearest_loc(business, lat, lng):
    for loc in Location.objects.filter(business=business):
        d = haversine_m(float(lat), float(lng), float(loc.lat), float(loc.lng))
        if d <= loc.radius_m:
            return loc
    return None

@login_required
def start_shift(request):
    if request.method != "POST": return HttpResponseBadRequest("POST only")
    agent = request.user.agent  # assuming 1â€“1
    biz = agent.business
    lat = request.POST.get("lat"); lng = request.POST.get("lng")
    tl = TimeLog.objects.create(agent=agent, business=biz)
    in_range = False
    if lat and lng:
        in_range = bool(_nearest_loc(biz, float(lat), float(lng)))
    TimeLogSegment.objects.create(timelog=tl, in_range=in_range)
    return JsonResponse({"ok": True, "timelog_id": tl.id, "in_range": in_range})

@login_required
def stop_shift(request, timelog_id):
    tl = get_object_or_404(TimeLog, id=timelog_id, agent__user=request.user, is_active=True)
    seg = tl.segments.order_by("-id").first()
    if seg and not seg.ended_at:
        seg.ended_at = timezone.now(); seg.save()
    tl.ended_at = timezone.now(); tl.is_active = False; tl.save()
    return JsonResponse({"ok": True, "work_min": tl.work_minutes, "out_min": tl.out_minutes})

@login_required
def gps_ping(request, timelog_id):
    """Called every ~10â€“20s from the browser while shift is active."""
    if request.method != "POST": return HttpResponseBadRequest("POST only")
    tl = get_object_or_404(TimeLog, id=timelog_id, agent__user=request.user, is_active=True)
    lat = float(request.POST["lat"]); lng = float(request.POST["lng"])
    in_range = bool(_nearest_loc(tl.business, lat, lng))
    last = tl.segments.order_by("-id").first()
    now = timezone.now()
    if last and last.in_range == in_range and not last.ended_at:
        # no state change â€” do nothing
        return JsonResponse({"ok": True, "in_range": in_range})
    # close previous
    if last and not last.ended_at:
        last.ended_at = now; last.save()
    # open new segment with flipped state
    TimeLogSegment.objects.create(timelog=tl, in_range=in_range, started_at=now)
    return JsonResponse({"ok": True, "in_range": in_range})





