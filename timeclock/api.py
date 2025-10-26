from django.utils.timezone import now
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from business.models import AgentAssignment
from .models import TimeSession
from .utils import haversine_m

@login_required
@require_POST
def heartbeat(request):
    try:
        lat=float(request.POST['lat']); lon=float(request.POST['lon']); acc=int(request.POST.get('acc',999))
    except Exception:
        return HttpResponseBadRequest("bad coords")

    assign = (AgentAssignment.objects
              .filter(user=request.user, active=True)
              .select_related('store').first())
    if not assign or not assign.store.latitude:
        return JsonResponse({"state":"no-store"})

    st = assign.store
    dist = haversine_m(lat,lon,st.latitude,st.longitude)
    in_range = dist <= max(st.geofence_radius_m, acc)  # be nice if GPS is fuzzy

    # find open session of this type
    open_qs = TimeSession.objects.filter(user=request.user, store=st, ended_at__isnull=True)
    now_ts = now()

    sess = open_qs.first()
    if not sess:
        # start
        sess = TimeSession.objects.create(user=request.user, store=st, in_range=in_range)
    else:
        # if state changed, close and start new
        if sess.in_range != in_range:
            sess.ended_at = now_ts
            sess.seconds = int((sess.ended_at - sess.started_at).total_seconds())
            sess.save()
            sess = TimeSession.objects.create(user=request.user, store=st, in_range=in_range)

    # return rolls for live display
    # compute current open session elapsed
    elapsed = int((now_ts - sess.started_at).total_seconds())
    day_total_work = (TimeSession.objects
        .filter(user=request.user, store=st, in_range=True, started_at__date=now_ts.date())
        .aggregate(sec=Sum('seconds'))['sec'] or 0) + (elapsed if sess.in_range else 0)
    day_total_away = (TimeSession.objects
        .filter(user=request.user, store=st, in_range=False, started_at__date=now_ts.date())
        .aggregate(sec=Sum('seconds'))['sec'] or 0) + (elapsed if not sess.in_range else 0)

    return JsonResponse({"state":"in" if in_range else "out",
                         "distance_m": round(dist),
                         "work_s": day_total_work,
                         "away_s": day_total_away})


